from __future__ import annotations

from bisect import bisect_right
from typing import Sequence

from PySide6.QtCore import QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter, QPainterPath, QPen
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoFrame, QVideoSink
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..services.alignment import Word
from ..services.subtitle_renderer import SubtitleStyle, animation_progress, font_fallback


class VideoPreview(QWidget):
    """Play a local video and paint its timed WordPop captions over each frame."""

    status_changed = Signal(str)
    position_changed = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(360, 250)
        self.setObjectName("videoPreview")
        self._frame = QImage()
        self._words: list[Word] = []
        self._starts: list[float] = []
        self._index = -1
        self._style = SubtitleStyle()
        self._auto_pause_on_first_frame = False

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.8)
        self.player.setAudioOutput(self.audio_output)
        self.video_sink = QVideoSink(self)
        self.player.setVideoSink(self.video_sink)
        self.video_sink.videoFrameChanged.connect(self._on_video_frame)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.player.errorOccurred.connect(self._on_player_error)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(30)
        self._refresh_timer.timeout.connect(self.update)
        self._refresh_timer.start()

    @property
    def current_index(self) -> int:
        return self._index

    def set_video(self, path: str) -> None:
        """Load a source and briefly start playback to acquire its first frame."""
        self.player.stop()
        self._frame = QImage()
        self._index = -1
        self._auto_pause_on_first_frame = True
        self.audio_output.setMuted(True)
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()
        self.status_changed.emit("Loading video preview...")
        self.update()

    def set_image(self, path: str) -> None:
        """Set a poster image, used when generating documentation screenshots."""
        self._frame = QImage(path)
        self.update()

    def set_words(self, words: Sequence[Word]) -> None:
        self._words = list(words)
        self._starts = [word.start for word in self._words]
        self._update_active_word(self.player.position())
        self.update()

    def set_style(self, style: SubtitleStyle) -> None:
        self._style = style
        self.update()

    def seek_to_word(self, index: int) -> None:
        if not self._words:
            return
        index = max(0, min(len(self._words) - 1, index))
        self._index = index
        self.player.setPosition(round(self._words[index].start * 1000))
        self.update()

    def next_word(self) -> None:
        if self._words:
            self.seek_to_word((self._index + 1) % len(self._words))

    def toggle_playback(self) -> None:
        if self.player.source().isEmpty():
            self.status_changed.emit("Choose a video to start full playback preview.")
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            if self.player.position() >= self.player.duration() > 0:
                self.player.setPosition(0)
            self.player.play()

    def seek_ms(self, position: int) -> None:
        self.player.setPosition(max(0, min(self.player.duration(), int(position))))

    def stop(self) -> None:
        self._refresh_timer.stop()
        self.player.stop()

    def _on_video_frame(self, frame: QVideoFrame) -> None:
        image = frame.toImage()
        if not image.isNull():
            self._frame = image
            self.update()
        if self._auto_pause_on_first_frame:
            self._auto_pause_on_first_frame = False
            self.player.pause()
            self.player.setPosition(0)
            self.audio_output.setMuted(False)
            self.status_changed.emit("Preview ready. Play to watch the video with timed subtitles.")

    def _on_position_changed(self, position: int) -> None:
        self._update_active_word(position)
        self.position_changed.emit(position, self.player.duration())
        self.update()

    def _on_duration_changed(self, duration: int) -> None:
        self.position_changed.emit(self.player.position(), duration)

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.status_changed.emit("Playing full video preview with synchronized captions.")
        elif self._frame.isNull() and not self.player.source().isEmpty():
            self.status_changed.emit("Waiting for the video decoder...")

    def _on_player_error(self, error: QMediaPlayer.Error, message: str) -> None:
        if error != QMediaPlayer.Error.NoError:
            self._auto_pause_on_first_frame = False
            self.audio_output.setMuted(False)
            self.status_changed.emit(f"Could not play this preview: {message or 'unsupported video or codec'}")

    def _update_active_word(self, position_ms: int) -> None:
        position = max(0, position_ms / 1000)
        candidate = bisect_right(self._starts, position) - 1
        active = candidate if candidate >= 0 and position < self._words[candidate].end else -1
        if active != self._index:
            self._index = active

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("#0c1017"))
        video_rect = self._video_rect()
        if self._frame.isNull():
            painter.setPen(QColor("#8d9bae"))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Choose a video to preview full playback",
            )
            return

        painter.drawImage(video_rect, self._frame)
        if not self._words or self._index < 0:
            return
        self._draw_captions(painter, video_rect)

    def _video_rect(self) -> QRectF:
        if self._frame.isNull() or self.width() <= 0 or self.height() <= 0:
            return QRectF(self.rect())
        size = self._frame.size()
        scale = min(self.width() / size.width(), self.height() / size.height())
        width = size.width() * scale
        height = size.height() * scale
        return QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)

    def _phrase_start(self, index: int) -> int:
        start = index
        maximum = max(1, min(8, self._style.phrase_length))
        while start > 0 and index - start + 1 < maximum:
            previous = self._words[start - 1]
            current = self._words[start]
            if previous.text.rstrip().endswith((".", "!", "?")) or current.start - previous.end > 0.65:
                break
            start -= 1
        return start

    def _draw_captions(self, painter: QPainter, video_rect: QRectF) -> None:
        current = self._words[self._index]
        if self._style.mode == "phrase":
            begin = self._phrase_start(self._index)
            phrase = self._words[begin:self._index + 1]
        else:
            phrase = [current]
        display = [word.text.upper() if self._style.uppercase else word.text for word in phrase]

        scale = video_rect.height() / 1080
        font_size = max(12, round(self._style.font_size * scale))
        font = QFont(font_fallback(self._style.font_family, QFontDatabase.families()))
        font.setBold(True)
        font.setPixelSize(font_size)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        gap = max(4, round(font_size * 0.24))
        widths = [metrics.horizontalAdvance(text) for text in display]
        total_width = sum(widths) + gap * max(0, len(widths) - 1)
        safe_width = video_rect.width() * (1 - 2 * max(0, min(40, self._style.margin_x)) / 100)
        if total_width > safe_width and total_width > 0:
            font_size = max(12, round(font_size * safe_width / total_width))
            font.setPixelSize(font_size)
            painter.setFont(font)
            metrics = painter.fontMetrics()
            gap = max(4, round(font_size * 0.24))
            widths = [metrics.horizontalAdvance(text) for text in display]
            total_width = sum(widths) + gap * max(0, len(widths) - 1)

        center_x = video_rect.center().x()
        position_percent = max(5, min(95, self._style.position_percent))
        baseline = video_rect.top() + video_rect.height() * position_percent / 100
        x = center_x - total_width / 2
        outline = max(1.0, self._style.outline_width * scale)
        video_margin_x = video_rect.width() * max(0, self._style.margin_x) / 100
        video_margin_y = video_rect.height() * max(0, self._style.margin_y) / 100
        painter.save()
        painter.setClipRect(video_rect.adjusted(video_margin_x, video_margin_y, -video_margin_x, -video_margin_y))
        elapsed_ms = max(0, self.player.position() - round(current.start * 1000))
        factor = (
            animation_progress(elapsed_ms, self._style.animation_ms, self._style.animation_intensity / 100)
            if self._style.pop_enabled
            else 1
        )
        for index, text in enumerate(display):
            active = index == len(display) - 1
            word_width = widths[index]
            cx = x + word_width / 2
            painter.save()
            if active:
                cy = baseline - font_size / 2
                painter.translate(cx, cy)
                painter.scale(factor, factor)
                painter.translate(-cx, -cy)
            text_path = QPainterPath()
            text_path.addText(x, baseline, font, text)
            painter.setPen(QPen(QColor(self._style.outline_color), outline, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(text_path)
            if self._style.shadow:
                shadow_path = QPainterPath(text_path)
                shadow_path.translate(1.5 * scale, 2.0 * scale)
                painter.setPen(QPen(QColor(0, 0, 0, 80), max(1, outline * 1.5), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                painter.drawPath(shadow_path)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self._style.active_color if active else self._style.text_color))
            painter.drawPath(text_path)
            painter.restore()
            x += word_width + (gap if index < len(display) - 1 else 0)
        painter.restore()


class PreviewCard(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        title = QLabel("VIDEO PREVIEW")
        title.setObjectName("eyebrow")
        self.cycle_button = QPushButton("Next word")
        self.cycle_button.setObjectName("ghostButton")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.cycle_button)
        self.preview = VideoPreview()

        controls = QHBoxLayout()
        self.play_button = QPushButton("Play")
        self.play_button.setObjectName("ghostButton")
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 10000)
        self.seek_slider.setEnabled(False)
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("mutedText")
        self.time_label.setMinimumWidth(92)
        controls.addWidget(self.play_button)
        controls.addWidget(self.seek_slider, 1)
        controls.addWidget(self.time_label)

        self.hint = QLabel("Choose a video to load full playback with timed subtitles.")
        self.hint.setObjectName("mutedText")
        self.hint.setWordWrap(True)
        layout.addLayout(header)
        layout.addWidget(self.preview, 1)
        layout.addLayout(controls)
        layout.addWidget(self.hint)

        self.cycle_button.clicked.connect(self.preview.next_word)
        self.play_button.clicked.connect(self.preview.toggle_playback)
        self.seek_slider.sliderMoved.connect(self._seek_from_slider)
        self.preview.status_changed.connect(self.hint.setText)
        self.preview.position_changed.connect(self._update_timeline)
        self.preview.player.playbackStateChanged.connect(self._update_play_button)

    def set_video(self, path: str) -> None:
        self.seek_slider.setEnabled(True)
        self.preview.set_video(path)

    def _seek_from_slider(self, value: int) -> None:
        duration = self.preview.player.duration()
        self.preview.seek_ms(round(duration * value / self.seek_slider.maximum()))

    def _update_timeline(self, position: int, duration: int) -> None:
        if duration > 0:
            if not self.seek_slider.isSliderDown():
                self.seek_slider.setValue(round(position * self.seek_slider.maximum() / duration))
            self.seek_slider.setEnabled(True)
        self.time_label.setText(f"{self._format_time(position)} / {self._format_time(duration)}")

    def _update_play_button(self, state: QMediaPlayer.PlaybackState) -> None:
        self.play_button.setText("Pause" if state == QMediaPlayer.PlaybackState.PlayingState else "Play")

    @staticmethod
    def _format_time(milliseconds: int) -> str:
        seconds = max(0, milliseconds // 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"
