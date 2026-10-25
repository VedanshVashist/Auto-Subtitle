from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

from .alignment import Word
from .subtitle_renderer import SubtitleStyle, render_ass
from ..utils.ffmpeg_utils import FFmpegError, VideoInfo, executable, probe_video

logger = logging.getLogger(__name__)
COPY_AUDIO_CODECS = {"aac", "mp3", "ac3", "eac3", "alac"}


class RenderCancelled(RuntimeError):
    pass


def _filter_path(path: Path) -> str:
    value = path.resolve().as_posix().replace("\\", "/")
    value = value.replace(":", r"\:").replace("'", r"\'")
    return f"subtitles='{value}'"


def _output_dimensions(info: VideoInfo, resolution: str) -> tuple[int, int]:
    if resolution == "Original":
        return info.width, info.height
    target_height = {"1080p": 1080, "720p": 720, "4K": 2160}.get(resolution)
    if not target_height:
        raise ValueError(f"Unsupported output resolution: {resolution}")
    target_width = round(info.width * target_height / info.height / 2) * 2
    return target_width, target_height


def render_video(
    input_path: Path,
    output_path: Path,
    words: list[Word],
    style: SubtitleStyle,
    *,
    crf: int = 20,
    resolution: str = "Original",
    progress: Callable[[int, str], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    temp_dir: Path | None = None,
    overwrite: bool = False,
) -> Path:
    source = Path(input_path).resolve()
    destination = Path(output_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Source video not found: {source}")
    if source == destination:
        raise ValueError("Output path must be different from the original video.")
    if destination.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {destination}")
    if destination.suffix.casefold() != ".mp4":
        raise ValueError("Output must use the .mp4 extension.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    info = probe_video(source)
    width, height = _output_dimensions(info, resolution)
    crf = max(15, min(30, int(crf)))
    scratch = Path(temp_dir) if temp_dir else destination.parent / ".wordpop-temp"
    scratch.mkdir(parents=True, exist_ok=True)
    ass_path = scratch / f"wordpop_{os.getpid()}_{time.time_ns()}.ass"
    partial_path = destination.with_name(destination.stem + f".{os.getpid()}_{time.time_ns()}.partial.mp4")
    ass_path.write_text(render_ass(words, width, height, style), encoding="utf-8-sig")
    video_filter = _filter_path(ass_path)
    if resolution != "Original":
        video_filter = f"scale={width}:{height}:flags=lanczos," + video_filter
    audio_args = ["-c:a", "copy"] if info.audio_codec in COPY_AUDIO_CODECS else ["-c:a", "aac", "-b:a", "192k"]
    if not info.has_audio:
        audio_args = ["-an"]
    command = [
        executable("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-map", "0:v:0", "-map", "0:a?", "-vf", video_filter, "-fps_mode", "passthrough",
        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
        *audio_args, "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(partial_path),
    ]
    if progress:
        progress(1, "Rendering animated captions with FFmpeg…")
    try:
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1) as process:
            last_lines: list[str] = []
            assert process.stdout is not None
            for line in process.stdout:
                line = line.rstrip()
                if line and "=" not in line:
                    last_lines.append(line)
                    last_lines = last_lines[-12:]
                    logger.debug("ffmpeg: %s", line)
                if is_cancelled and is_cancelled():
                    process.terminate()
                    try:
                        process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    raise RenderCancelled("Render cancelled.")
                if line.startswith("out_time_ms=") and progress:
                    try:
                        elapsed = int(line.split("=", 1)[1]) / 1_000_000
                        percent = min(99, max(2, round(elapsed / info.duration * 100)))
                        progress(percent, f"Rendering {min(elapsed, info.duration):.1f}s / {info.duration:.1f}s…")
                    except ValueError:
                        pass
            code = process.wait()
        if code != 0:
            raise FFmpegError("FFmpeg could not render this video:\n" + "\n".join(last_lines[-8:]))
        if not partial_path.is_file() or partial_path.stat().st_size < 1024:
            raise FFmpegError("FFmpeg finished without creating a valid output file.")
        result_info = probe_video(partial_path)
        if result_info.duration <= 0:
            raise FFmpegError("The exported MP4 failed validation: no video duration was found.")
        if info.has_audio and not result_info.has_audio:
            raise FFmpegError("The source has audio, but the exported MP4 does not.")
        if overwrite:
            os.replace(partial_path, destination)
        else:
            # On Windows os.rename fails atomically when the destination appeared after
            # the initial check, so a concurrent file is never silently replaced.
            os.rename(partial_path, destination)
        if progress:
            progress(100, f"Export complete: {destination.name}")
        return destination
    except RenderCancelled:
        raise
    except FileExistsError:
        raise
    except (OSError, subprocess.SubprocessError, FFmpegError) as exc:
        if isinstance(exc, FFmpegError):
            raise
        raise FFmpegError(f"Video rendering failed: {exc}") from exc
    finally:
        try:
            ass_path.unlink(missing_ok=True)
            partial_path.unlink(missing_ok=True)
            if not any(scratch.iterdir()) and scratch.name == ".wordpop-temp":
                scratch.rmdir()
        except OSError:
            logger.warning("Could not remove temporary render files in %s", scratch)
