from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class SystemInfo:
    operating_system: str
    architecture: str
    python_version: str
    cpu_count: int
    ram_gib: float | None
    gpu_name: str
    gpu_acceleration_available: bool
    ffmpeg: str | None
    ffprobe: str | None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _windows_ram_gib() -> float | None:
    if os.name != "nt":
        return None
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        return round(int(result.stdout.strip()) / (1024 ** 3), 1)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def detect_system_info() -> SystemInfo:
    gpu_name = "Unknown"
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_VideoController | Select-Object -First 1 -ExpandProperty Name)"],
                capture_output=True, text=True, timeout=5, check=True,
            )
            gpu_name = result.stdout.strip() or gpu_name
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        gpu_name = "GPU detection unavailable"

    # faster-whisper GPU inference currently requires a compatible NVIDIA CUDA stack.
    gpu_ready = bool(shutil.which("nvidia-smi"))
    if gpu_ready:
        try:
            subprocess.run(["nvidia-smi", "-L"], capture_output=True, timeout=4, check=True)
        except (OSError, subprocess.SubprocessError):
            gpu_ready = False

    return SystemInfo(
        operating_system=f"{platform.system()} {platform.release()}",
        architecture=platform.machine(),
        python_version=platform.python_version(),
        cpu_count=os.cpu_count() or 1,
        ram_gib=_windows_ram_gib(),
        gpu_name=gpu_name,
        gpu_acceleration_available=gpu_ready,
        ffmpeg=shutil.which("ffmpeg"),
        ffprobe=shutil.which("ffprobe"),
    )


def free_space_gib(path: str | Path) -> float:
    return round(shutil.disk_usage(Path(path).resolve()).free / (1024 ** 3), 2)
