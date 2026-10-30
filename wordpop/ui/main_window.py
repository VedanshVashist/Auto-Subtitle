from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import QStandardPaths, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QSplitter, QVBoxLayout, QWidget, QSpinBox,
    QLineEdit, QInputDialog,
)

from ..services.alignment import Word, load_transcript, save_transcript
from ..services.video_processor import VideoInfo
from ..utils.config_manager import ConfigManager
from ..utils.ffmpeg_utils import FFmpegError, probe_video, unique_output_path
from ..utils.logging_utils import configure_logging
from ..utils.system_info import detect_system_info, free_space_gib
from .preview import PreviewCard
from .settings_panel import SettingsPanel
from .transcript_editor import TranscriptEditor
from .workers import RenderWorker, TranscriptionWorker

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, startup_path: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle("WordPop Studio")
        self.resize(1440, 960)
        self.setMinimumSize(1180, 760)
        self.setAcceptDrops(True)
        self.media_path: Path | None = None
        self.media_info: VideoInfo | None = None
        self.worker: TranscriptionWorker | RenderWorker | None = None
        self._workers: list[TranscriptionWorker | RenderWorker] = []
        self.language_detected = "auto"
        self.last_output: Path | None = None
        self.app_data_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        self.system_info = detect_system_info()
        project_root = Path(__file__).resolve().parents[2]
        self.config = ConfigManager(
            self.app_data_dir / "settings.json",
            self.app_data_dir / "custom-presets.json",
            project_root / "config" / "presets.json",
        )
        self.settings = self.config.load()
        self.log_path = configure_logging(self.app_data_dir / "logs")
        self._build_ui()
        self._set_ready_status("Ready · everything runs locally on this computer")
        if startup_path:
            self.open_video(Path(startup_path))

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(14)

        top = QHBoxLayout()
        brand = QVBoxLayout()
        name = QLabel("WordPop Studio")
        name.setObjectName("brandTitle")
        subtitle = QLabel("LOCAL AI SUBTITLES  ·  WORD BY WORD")
        subtitle.setObjectName("eyebrow")
        brand.addWidget(name)
        brand.addWidget(subtitle)
        top.addLayout(brand)
        top.addStretch()
        self.open_button = QPushButton("Choose video")
        self.open_button.setObjectName("primaryButton")
        self.open_button.clicked.connect(self.choose_video)
        top.addWidget(self.open_button)
        self.load_transcript_button = QPushButton("Load transcript")
        self.load_transcript_button.setObjectName("ghostButton")
        self.load_transcript_button.clicked.connect(self.load_transcript_dialog)
        top.addWidget(self.load_transcript_button)
        self.save_transcript_button = QPushButton("Save transcript")
        self.save_transcript_button.setObjectName("ghostButton")
        self.save_transcript_button.clicked.connect(self.save_transcript_dialog)
        top.addWidget(self.save_transcript_button)
        root.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(12)
        self.preview_card = PreviewCard()
        left_layout.addWidget(self.preview_card, 3)
        self.media_info_label = QLabel("Drop an MP4, MOV, MKV or WebM video here")
        self.media_info_label.setObjectName("mediaInfo")
        left_layout.addWidget(self.media_info_label)
        transcript_box = QWidget()
        transcript_layout = QVBoxLayout(transcript_box)
        transcript_layout.setContentsMargins(0, 0, 0, 0)
        transcript_layout.setSpacing(6)
        self.editor = TranscriptEditor()
        transcript_layout.addWidget(self.editor)
        left_layout.addWidget(transcript_box, 2)
        self.editor.word_selected.connect(self.preview_card.preview.seek_to_word)
        self.editor.changed.connect(self._transcript_edited)
        self.preview_card.cycle_button.clicked.connect(self._select_next_preview_row)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(12)
        section = QLabel("CAPTION & EXPORT SETTINGS")
        section.setObjectName("eyebrow")
        right_layout.addWidget(section)
        self.settings_panel = SettingsPanel(sorted(self.config.presets), self.settings)
        self.settings_panel.settings_changed.connect(self._settings_changed)
        self.settings_panel.preset_selected.connect(self._apply_preset)
        self.settings_panel.save_preset_requested.connect(self._save_preset_prompt)
        self.settings_panel.rename_preset_requested.connect(self._rename_preset_prompt)
        self.settings_panel.delete_preset_requested.connect(self._delete_preset_prompt)
        right_layout.addWidget(self.settings_panel, 1)

        export_group = QWidget()
        export_layout = QVBoxLayout(export_group)
        export_layout.setContentsMargins(0, 0, 0, 0)
        export_layout.setSpacing(8)
        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText("Output video file…")
        self.output_browse_button = QPushButton("Browse")
        self.output_browse_button.setObjectName("ghostButton")
        self.output_browse_button.clicked.connect(self.choose_output)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_path, 1)
        output_row.addWidget(self.output_browse_button)
        export_layout.addLayout(output_row)
        export_form = QFormLayout()
        self.resolution = QComboBox()
        self.resolution.addItems(["Original", "1080p", "720p", "4K"])
        self.resolution.setCurrentText(str(self.settings.get("resolution", "Original")))
        self.quality = QSpinBox()
        self.quality.setRange(15, 30)
        self.quality.setValue(int(self.settings.get("crf", 20)))
        self.quality.setToolTip("Lower CRF gives better quality and a larger file. 20 is a good default.")
        self.resolution.currentTextChanged.connect(self._export_settings_changed)
        self.quality.valueChanged.connect(self._export_settings_changed)
        export_form.addRow("Output size", self.resolution)
        export_form.addRow("H.264 quality (CRF)", self.quality)
        export_layout.addLayout(export_form)
        action_row = QHBoxLayout()
        self.transcribe_button = QPushButton("Transcribe")
        self.transcribe_button.setObjectName("primaryButton")
        self.transcribe_button.clicked.connect(self.start_transcription)
        self.export_button = QPushButton("Export MP4")
        self.export_button.setObjectName("successButton")
        self.export_button.clicked.connect(self.start_render)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("dangerButton")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_work)
        action_row.addWidget(self.transcribe_button, 1)
        action_row.addWidget(self.export_button, 1)
        action_row.addWidget(self.cancel_button)
        export_layout.addLayout(action_row)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        export_layout.addWidget(self.progress)
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusText")
        self.status_label.setWordWrap(True)
        export_layout.addWidget(self.status_label)
        self.open_output_button = QPushButton("Open output folder")
        self.open_output_button.setObjectName("ghostButton")
        self.open_output_button.clicked.connect(self.open_output_folder)
        export_layout.addWidget(self.open_output_button, alignment=Qt.AlignmentFlag.AlignRight)
        ram = f"{self.system_info.ram_gib:g} GB RAM" if self.system_info.ram_gib is not None else "RAM unknown"
        gpu = "NVIDIA GPU ready" if self.system_info.gpu_acceleration_available else f"CPU int8 · {self.system_info.gpu_name}"
        self.machine_label = QLabel(f"{self.system_info.cpu_count} logical CPU threads  ·  {ram}  ·  {gpu}")
        self.machine_label.setObjectName("mutedText")
        self.machine_label.setWordWrap(True)
        export_layout.addWidget(self.machine_label)
        right_layout.addWidget(export_group)
        splitter.addWidget(right)
        splitter.setSizes([810, 570])
        root.addWidget(splitter, 1)

        self.setStatusBarMessage(f"Logs: {self.log_path}")
        self._apply_settings_style()

    def setStatusBarMessage(self, text: str) -> None:
        self.statusBar().showMessage(text)

    def choose_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a video", str(Path.home()), "Videos (*.mp4 *.mov *.mkv *.webm *.avi);;All files (*.*)")
        if path:
            self.open_video(Path(path))

    def open_video(self, path: Path) -> None:
        try:
            info = probe_video(path)
            self.media_path, self.media_info = info.path, info
            self.preview_card.set_video(str(info.path))
            audio = f"Audio · {info.audio_codec}" if info.has_audio else "No audio track"
            self.media_info_label.setText(f"{info.path.name}  ·  {info.resolution}  ·  {info.fps:.2f} fps  ·  {info.duration:.2f}s  ·  {audio}")
            default_output = unique_output_path(Path(__file__).resolve().parents[2] / "output", f"{info.path.stem}_WordPop")
            self.output_path.setText(str(default_output))
            self.editor.set_words([])
            self.preview_card.preview.set_words([])
            self.settings["resolution"] = self.resolution.currentText()
            logger.info("Selected video: %s (%s, %.2fs)", info.path, info.resolution, info.duration)
            transcript_candidate = Path(__file__).resolve().parents[2] / "output" / f"{info.path.stem}.wordpop.json"
            if transcript_candidate.is_file():
                try:
                    words, language = load_transcript(transcript_candidate, info.duration)
                    self.editor.set_words(words)
                    self.preview_card.preview.set_words(words)
                    self.language_detected = language
                    self._set_ready_status(f"Video and reusable transcript loaded · {len(words)} words · {language}")
                except Exception as exc:
                    logger.warning("Could not load saved transcript %s: %s", transcript_candidate, exc)
                    self._set_ready_status(f"Video ready · saved transcript could not be loaded: {exc}")
            else:
                self._set_ready_status("Video ready · choose Transcribe to create word-level timestamps")
        except Exception as exc:
            logger.exception("Could not open video %s", path)
            QMessageBox.critical(self, "Could not open video", str(exc))

    def _settings_changed(self, values: dict[str, Any]) -> None:
        self.settings.update(values)
        self.settings["resolution"] = self.resolution.currentText() if hasattr(self, "resolution") else "Original"
        self.settings["crf"] = self.quality.value() if hasattr(self, "quality") else 20
        self.config.save(self.settings)
        self._apply_settings_style()

    def _export_settings_changed(self, *args) -> None:
        if not hasattr(self, "resolution") or not hasattr(self, "quality"):
            return
        self.settings["resolution"] = self.resolution.currentText()
        self.settings["crf"] = self.quality.value()
        self.config.save(self.settings)

    def _apply_settings_style(self) -> None:
        if hasattr(self, "settings_panel"):
            self.preview_card.preview.set_style(self.settings_panel.style())

    def _apply_preset(self, name: str) -> None:
        if not name or name not in self.config.presets:
            return
        try:
            values = self.config.apply_preset(name)
            self.settings.update(values)
            self.settings_panel.set_values(self.settings)
            self._settings_changed(self.settings_panel.values())
            self.settings["preset"] = name
        except Exception as exc:
            QMessageBox.warning(self, "Preset", str(exc))

    def _save_preset_prompt(self) -> None:
        name, accepted = QInputDialog.getText(self, "Save preset", "Preset name:")
        if not accepted:
            return
        try:
            self.config.save_preset(name, self.settings_panel.values())
            self.settings_panel.refresh_presets(sorted(self.config.presets), name.strip())
            self.status_label.setText(f"Saved preset '{name.strip()}'.")
        except Exception as exc:
            QMessageBox.warning(self, "Could not save preset", str(exc))

    def _rename_preset_prompt(self, old_name: str) -> None:
        name, accepted = QInputDialog.getText(self, "Rename preset", "New name:", text=old_name)
        if not accepted:
            return
        try:
            self.config.rename_preset(old_name, name)
            self.settings_panel.refresh_presets(sorted(self.config.presets), name.strip())
        except Exception as exc:
            QMessageBox.warning(self, "Could not rename preset", str(exc))

    def _delete_preset_prompt(self, name: str) -> None:
        answer = QMessageBox.question(self, "Delete preset", f"Delete '{name}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.config.delete_preset(name)
            self.settings_panel.refresh_presets(sorted(self.config.presets), "Classic WordPop")
        except Exception as exc:
            QMessageBox.warning(self, "Could not delete preset", str(exc))

    def _transcript_edited(self) -> None:
        try:
            words = self.editor.get_words(self.media_info.duration if self.media_info else None)
            self.preview_card.preview.set_words(words)
            self.status_label.setText(f"Transcript edited · {len(words)} words · save to keep corrections")
        except ValueError:
            pass

    def _select_next_preview_row(self) -> None:
        if self.editor.table.rowCount():
            row = self.editor.table.currentRow()
            if row < 0:
                row = self.preview_card.preview.current_index
            self.editor.table.selectRow((row + 1) % self.editor.table.rowCount())
        else:
            self.preview_card.preview.next_word()

    def start_transcription(self) -> None:
        if self._busy():
            return
        if not self.media_path or not self.media_info:
            self.choose_video()
            if not self.media_path or not self.media_info:
                return
        if not self.media_info.has_audio:
            QMessageBox.warning(self, "No audio track", "This video has no audio stream to transcribe.")
            return
        values = self.settings_panel.values()
        required_gib = {"tiny": 0.4, "base": 0.6, "small": 1.0, "medium": 2.0, "large-v3": 4.0}.get(str(values["model"]), 1.0)
        available_gib = free_space_gib(self.app_data_dir)
        if available_gib < required_gib:
            QMessageBox.warning(self, "Low disk space", f"The selected model may need about {required_gib:.1f} GB available; only {available_gib:.2f} GB is free on the model cache drive.")
            return
        worker = TranscriptionWorker(
            self.media_path, model=str(values["model"]), language=str(values["language"]),
            cache_dir=self.app_data_dir / "models", duration=self.media_info.duration,
            prefer_gpu=self.system_info.gpu_acceleration_available,
        )
        self.worker = worker
        worker.progress.connect(self._progress_update)
        worker.completed.connect(self._transcription_complete)
        worker.failed.connect(self._work_failed)
        worker.cancelled.connect(self._work_cancelled)
        self._track_worker(worker)
        self._begin_work(f"Starting offline {values['model']} transcription…")
        worker.start()

    def _transcription_complete(self, words: list[Word], language: str, engine: str) -> None:
        self.editor.set_words(words)
        self.preview_card.preview.set_words(words)
        self.language_detected = language
        self.progress.setValue(100)
        self._end_work(f"Transcription complete · {len(words)} words · {language} · {engine}")
        if self.media_path:
            save_to = Path(__file__).resolve().parents[2] / "output" / f"{self.media_path.stem}.wordpop.json"
            try:
                save_transcript(save_to, words, source_video=str(self.media_path), language=language)
                self.status_label.setText(f"Transcript ready and saved · {save_to.name} · {engine}")
            except OSError as exc:
                logger.warning("Could not autosave transcript: %s", exc)

    def load_transcript_dialog(self) -> None:
        initial = str(Path(__file__).resolve().parents[2] / "output")
        path, _ = QFileDialog.getOpenFileName(self, "Load WordPop transcript", initial, "WordPop transcript (*.json);;JSON files (*.json)")
        if path:
            try:
                words, language = load_transcript(Path(path), self.media_info.duration if self.media_info else None)
                self.editor.set_words(words)
                self.preview_card.preview.set_words(words)
                self.language_detected = language
                self._set_ready_status(f"Loaded transcript · {len(words)} words · {language}")
            except Exception as exc:
                QMessageBox.critical(self, "Could not load transcript", str(exc))

    def save_transcript_dialog(self) -> None:
        try:
            words = self.editor.get_words(self.media_info.duration if self.media_info else None)
        except ValueError as exc:
            QMessageBox.warning(self, "Check transcript", str(exc))
            return
        default_name = f"{self.media_path.stem if self.media_path else 'transcript'}.wordpop.json"
        path, _ = QFileDialog.getSaveFileName(self, "Save transcript", str(Path(__file__).resolve().parents[2] / "output" / default_name), "WordPop transcript (*.json)")
        if path:
            try:
                save_transcript(Path(path), words, source_video=str(self.media_path or ""), language=self.language_detected)
                self._set_ready_status(f"Transcript saved · {Path(path).name}")
            except Exception as exc:
                QMessageBox.critical(self, "Could not save transcript", str(exc))

    def choose_output(self) -> None:
        default = self.output_path.text().strip() or str(Path(__file__).resolve().parents[2] / "output" / "WordPop.mp4")
        path, _ = QFileDialog.getSaveFileName(self, "Export subtitled video", default, "MP4 video (*.mp4)")
        if path:
            if not path.casefold().endswith(".mp4"):
                path += ".mp4"
            self.output_path.setText(path)

    def start_render(self) -> None:
        if self._busy():
            return
        if not self.media_path:
            QMessageBox.information(self, "Choose a video", "Select a source video before exporting.")
            self.choose_video()
            if not self.media_path:
                return
        try:
            words = self.editor.get_words(self.media_info.duration if self.media_info else None)
            if not words:
                QMessageBox.information(self, "Transcribe first", "Create or load a transcript before exporting.")
                return
        except ValueError as exc:
            QMessageBox.warning(self, "Check transcript timing", str(exc))
            return
        output = Path(self.output_path.text().strip()) if self.output_path.text().strip() else unique_output_path(Path(__file__).resolve().parents[2] / "output", f"{self.media_path.stem}_WordPop")
        overwrite = False
        if output.exists():
            answer = QMessageBox.question(self, "Replace output?", f"This file already exists:\n{output}\n\nReplace it after a successful render?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                output = unique_output_path(output.parent, output.stem)
                self.output_path.setText(str(output))
            else:
                overwrite = True
        space_path = output.parent if output.parent.exists() else Path(output.anchor)
        available_gib = free_space_gib(space_path)
        required_gib = max(0.5, self.media_path.stat().st_size * 1.5 / (1024 ** 3))
        if available_gib < required_gib:
            answer = QMessageBox.question(
                self, "Low disk space",
                f"The render may need around {required_gib:.2f} GB, but only {available_gib:.2f} GB is free. Continue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        worker = RenderWorker(
            self.media_path, output, words, self.settings_panel.style(),
            quality=self.quality.value(), resolution=self.resolution.currentText(),
            temp_dir=Path(__file__).resolve().parents[2] / "temp", overwrite=overwrite,
        )
        self.worker = worker
        worker.progress.connect(self._progress_update)
        worker.completed.connect(self._render_complete)
        worker.failed.connect(self._work_failed)
        worker.cancelled.connect(self._work_cancelled)
        self._track_worker(worker)
        self._begin_work("Rendering captions into the MP4 in one FFmpeg pass…")
        worker.start()

    def cancel_work(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.status_label.setText("Cancelling safely after the current model step…")
            self.cancel_button.setEnabled(False)

    def _progress_update(self, value: int, text: str) -> None:
        self.progress.setValue(value)
        self.status_label.setText(text)

    def _render_complete(self, path: str) -> None:
        self.last_output = Path(path)
        self.progress.setValue(100)
        self._end_work(f"Export complete · {self.last_output.name}")
        QMessageBox.information(self, "Video ready", f"Subtitles are embedded in the MP4:\n{path}")

    def _work_failed(self, message: str) -> None:
        logger.error("Background operation failed: %s", message)
        self._end_work(f"Could not finish · {message}")
        QMessageBox.critical(self, "WordPop Studio error", message)

    def _work_cancelled(self) -> None:
        self.progress.setValue(0)
        self._end_work("Operation cancelled · temporary output was removed")

    def _begin_work(self, message: str) -> None:
        self.progress.setValue(0)
        self.status_label.setText(message)
        self.open_button.setEnabled(False)
        self.transcribe_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.cancel_button.setEnabled(True)

    def _end_work(self, message: str) -> None:
        self.status_label.setText(message)
        self.open_button.setEnabled(True)
        self.transcribe_button.setEnabled(True)
        self.export_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def _track_worker(self, worker: TranscriptionWorker | RenderWorker) -> None:
        self._workers.append(worker)
        worker.finished.connect(lambda current=worker: self._worker_finished(current))

    def _worker_finished(self, worker: TranscriptionWorker | RenderWorker) -> None:
        if worker in self._workers:
            self._workers.remove(worker)
        if self.worker is worker:
            self.worker = None

    def _busy(self) -> bool:
        return bool(self.worker and self.worker.isRunning())

    def open_output_folder(self) -> None:
        target = self.last_output.parent if self.last_output else Path(__file__).resolve().parents[2] / "output"
        target.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.resolve())))

    def _set_ready_status(self, message: str) -> None:
        self.status_label.setText(message)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.preview_card.preview.stop()
        super().closeEvent(event)
        self.progress.setValue(0)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        if urls:
            self.open_video(Path(urls[0].toLocalFile()))
            event.acceptProposedAction()

    def closeEvent(self, event) -> None:  # noqa: N802
        running = [worker for worker in self._workers if worker.isRunning()]
        for worker in running:
            worker.cancel()
        if running and not all(worker.wait(5000) for worker in running):
            QMessageBox.information(self, "Finishing current task", "The worker is still finishing a safe cancellation step. Wait for cancellation to complete, then close WordPop Studio.")
            event.ignore()
            return
        try:
            self.config.save(self.settings_panel.values())
        except OSError:
            logger.exception("Could not save app preferences")
        super().closeEvent(event)
