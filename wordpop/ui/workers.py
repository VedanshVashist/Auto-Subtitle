from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..services.alignment import Word
from ..services.subtitle_renderer import SubtitleStyle
from ..services.transcription import TranscriptionCancelled, transcribe_file
from ..services.video_processor import RenderCancelled, render_video


class TranscriptionWorker(QThread):
    progress = Signal(int, str)
    completed = Signal(object, str, str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, path: Path, *, model: str, language: str, cache_dir: Path, duration: float, prefer_gpu: bool) -> None:
        super().__init__()
        self.path, self.model, self.language = path, model, language
        self.cache_dir, self.duration, self.prefer_gpu = cache_dir, duration, prefer_gpu
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def run(self) -> None:
        try:
            words, language, engine = transcribe_file(
                self.path, model_name=self.model, language=self.language, cache_dir=self.cache_dir,
                duration=self.duration, progress=self.progress.emit, is_cancelled=self._cancelled.is_set,
                prefer_gpu=self.prefer_gpu,
            )
            self.completed.emit(words, language, engine)
        except TranscriptionCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class RenderWorker(QThread):
    progress = Signal(int, str)
    completed = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, input_path: Path, output_path: Path, words: list[Word], style: SubtitleStyle,
                 *, quality: int, resolution: str, temp_dir: Path, overwrite: bool = False) -> None:
        super().__init__()
        self.input_path, self.output_path, self.words, self.style = input_path, output_path, words, style
        self.quality, self.resolution, self.temp_dir, self.overwrite = quality, resolution, temp_dir, overwrite
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def run(self) -> None:
        try:
            result = render_video(
                self.input_path, self.output_path, self.words, self.style,
                crf=self.quality, resolution=self.resolution, progress=self.progress.emit,
                is_cancelled=self._cancelled.is_set, temp_dir=self.temp_dir, overwrite=self.overwrite,
            )
            self.completed.emit(str(result))
        except RenderCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))
