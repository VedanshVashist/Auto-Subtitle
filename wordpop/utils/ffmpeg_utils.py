from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoInfo:
    path: Path
    duration: float
    width: int
    height: int
    fps: float
    video_codec: str
    audio_codec: str | None
    has_audio: bool

    @property
    def resolution(self) -> str:
        return f"{self.width} × {self.height}"


def executable(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise FFmpegError(f"{name} is not installed or is missing from PATH.")
    return found


def probe_video(path: Path) -> VideoInfo:
    video_path = Path(path)
    if not video_path.is_file():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    command = [executable("ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video_path)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=True)
        metadata = json.loads(result.stdout)
    except subprocess.CalledProcessError as exc:
        raise FFmpegError(f"FFprobe could not read this video: {exc.stderr.strip()}") from exc
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise FFmpegError(f"Could not inspect video: {exc}") from exc
    streams = metadata.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    if not video:
        raise FFmpegError("This file does not contain a video stream.")
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    duration = float(metadata.get("format", {}).get("duration") or video.get("duration") or 0)
    rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"
    try:
        num, den = (float(value) for value in rate.split("/", 1))
        fps = num / den if den else 0
    except (ValueError, ZeroDivisionError):
        fps = 0
    if duration <= 0:
        raise FFmpegError("Could not determine the video duration.")
    return VideoInfo(
        path=video_path.resolve(), duration=duration,
        width=int(video.get("width", 0)), height=int(video.get("height", 0)), fps=fps,
        video_codec=str(video.get("codec_name", "unknown")),
        audio_codec=str(audio.get("codec_name")) if audio else None,
        has_audio=audio is not None,
    )


def extract_thumbnail(path: Path, output_path: Path, *, at_seconds: float = 1.0, max_width: int = 900) -> Path:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Video file not found: {source}")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        executable("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-ss", str(max(0, at_seconds)),
        "-i", str(source), "-frames:v", "1", "-vf", f"scale='min({max_width},iw)':-2", str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if result.returncode != 0 or not output.is_file():
        raise FFmpegError(f"Could not create the video preview: {result.stderr.strip()}")
    return output


def unique_output_path(folder: Path, stem: str, suffix: str = ".mp4") -> Path:
    directory = Path(folder)
    directory.mkdir(parents=True, exist_ok=True)
    safe_stem = Path(stem).stem.strip(" .") or "WordPop"
    candidate = directory / f"{safe_stem}{suffix}"
    index = 2
    while candidate.exists():
        candidate = directory / f"{safe_stem}_{index}{suffix}"
        index += 1
    return candidate
