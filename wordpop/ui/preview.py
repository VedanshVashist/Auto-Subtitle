from __future__ import annotations

import time
from typing import Sequence

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QWidget

from ..services.alignment import Word
from ..services.subtitle_renderer import SubtitleStyle, animation_progress, font_fallback


class VideoPreview(QWidget):
    """Poster-frame preview with the same outline, word highlight and pop timing as export."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(360, 340)
        self.setObjectName("videoPreview")
        self._pixmap = QPixmap()
        self._words: list[Word] = [Word("Tokyo", 0, 1), Word("story", 1, 2), Word("happened", 2, 3), Word("today", 3, 4)]
        self._index = 0
        self._style = SubtitleStyle()
        self._word_started = time.monotonic()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(30)

    def set_image(self, path: str) -> None:
        self._pixmap = QPixmap(path)
        self.update()

    def set_style(self, style: SubtitleStyle) -> None:
        self._style = style
        self.update()

    def set_words(self, words: Sequence[Word]) -> None:
        self._words = list(words) or [Word("Tokyo", 0, 1)]
        self._index = min(self._index, len(self._words) - 1)
        self._word_started = time.monotonic()
        self.update()

    def set_index(self, index: int) -> None:
        if self._words:
            self._index = max(0, min(len(self._words) - 1, index))
            self._word_started = time.monotonic()
            self.update()

    def next_word(self) -> None:
        self.set_index((self._index + 1) % max(1, len(self._words)))

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0c1017"))
        if not self._pixmap.isNull():
            scaled = self._pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            painter.setPen(QColor("#8d9bae"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Choose a video to preview captions")
        # A slight veil matches the export's contrast without adding a caption box.
        painter.fillRect(self.rect(), QColor(5, 8, 12, 38))
        if not self._words:
            return
        current = self._words[self._index]
        if self._style.mode == "phrase":
            begin = max(0, self._index - max(1, min(8, self._style.phrase_length)) + 1)
            phrase = self._words[begin:self._index + 1]
        else:
            phrase = [current]
        if self._style.uppercase:
            phrase = [Word(item.text.upper(), item.start, item.end, item.confidence, item.timing) for item in phrase]
        scale_to_preview = self.height() / 1080
        pixel_size = max(12, round(self._style.font_size * scale_to_preview))
        font_name = font_fallback(self._style.font_family, QFontDatabase.families())
        font = QFont(font_name)
        font.setBold(True)
        font.setPixelSize(pixel_size)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        sizes = [metrics.horizontalAdvance(item.text) for item in phrase]
        gaps = max(0, len(phrase) - 1) * max(6, round(pixel_size * 0.24))
        total_width = sum(sizes) + gaps
        safe_width = max(20, self.width() * (1 - max(0, min(40, self._style.margin_x)) / 50))
        if total_width > safe_width and total_width:
            font.setPixelSize(max(12, round(pixel_size * safe_width / total_width)))
            pixel_size = font.pixelSize()
            metrics = painter.fontMetrics()
            sizes = [metrics.horizontalAdvance(item.text) for item in phrase]
            gaps = max(0, len(phrase) - 1) * max(6, round(pixel_size * 0.24))
            total_width = sum(sizes) + gaps
        center_x = self.width() / 2
        baseline = self.height() * max(5, min(95, self._style.position_percent)) / 100
        x = center_x - total_width / 2
        outline = max(1.0, self._style.outline_width * scale_to_preview)
        active_color = QColor(self._style.active_color)
        text_color = QColor(self._style.text_color)
        outline_color = QColor(self._style.outline_color)
        elapsed_ms = (time.monotonic() - self._word_started) * 1000
        factor = animation_progress(elapsed_ms, self._style.animation_ms, self._style.animation_intensity / 100) if self._style.pop_enabled else 1
        for index, item in enumerate(phrase):
            word_width = sizes[index]
            active = index == len(phrase) - 1
            cx = x + word_width / 2
            painter.save()
            if active:
                painter.translate(cx, baseline - pixel_size / 2)
                painter.scale(factor, factor)
                painter.translate(-cx, -(baseline - pixel_size / 2))
            text_path = QPainterPath()
            text_path.addText(x, baseline, font, item.text)
            painter.setPen(QPen(outline_color, outline, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(text_path)
            if self._style.shadow:
                shadow_path = QPainterPath(text_path)
                shadow_path.translate(1.5 * scale_to_preview, 2.0 * scale_to_preview)
                painter.setPen(QPen(QColor(0, 0, 0, 80), max(1, outline * 1.5), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                painter.drawPath(shadow_path)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(active_color if active else text_color)
            painter.drawPath(text_path)
            painter.restore()
            x += word_width + (max(6, round(pixel_size * 0.24)) if index < len(phrase) - 1 else 0)


class PreviewCard(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        title = QLabel("PREVIEW")
        title.setObjectName("eyebrow")
        self.cycle_button = QPushButton("Next word  ›")
        self.cycle_button.setObjectName("ghostButton")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.cycle_button)
        self.preview = VideoPreview()
        self.hint = QLabel("Style preview · select a transcript word to inspect it")
        self.hint.setObjectName("mutedText")
        layout.addLayout(header)
        layout.addWidget(self.preview, 1)
        layout.addWidget(self.hint)
        self.cycle_button.clicked.connect(self.preview.next_word)
