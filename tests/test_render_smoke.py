import shutil
import subprocess
from pathlib import Path

import pytest

from wordpop.services.alignment import Word
from wordpop.services.subtitle_renderer import SubtitleStyle
from wordpop.services.video_processor import render_video
from wordpop.utils.ffmpeg_utils import probe_video


def _source_video(tmp_path: Path) -> Path:
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg and FFprobe are required for the render smoke test")
    provided = Path(__file__).resolve().parents[2] / "Video3.mp4"
    sample = tmp_path / "input-sample.mp4"
    if provided.is_file():
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(provided), "-t", "1.8", "-map", "0:v:0", "-map", "0:a?", "-c", "copy", str(sample)]
    else:
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=navy:s=480x854:r=25:d=1.8", "-f", "lavfi", "-i", "sine=frequency=440:duration=1.8", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(sample)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=45)
    if result.returncode:
        pytest.fail(f"Could not create test source clip: {result.stderr}")
    return sample


def test_render_embeds_captions_and_keeps_source_audio(tmp_path):
    source = _source_video(tmp_path)
    source_info = probe_video(source)
    assert source_info.has_audio
    output = tmp_path / "rendered.mp4"
    rendered = render_video(
        source, output, [Word("Test", 0.25, 1.25)], SubtitleStyle(),
        crf=24, temp_dir=tmp_path / "render-temp",
    )
    assert rendered.is_file() and rendered.stat().st_size > 1024
    rendered_info = probe_video(rendered)
    assert rendered_info.width > 0 and rendered_info.height > 0
    assert rendered_info.has_audio
