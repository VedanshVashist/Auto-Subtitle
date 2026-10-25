"""Capture fresh, media-free screenshots for the README."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFontDatabase, QLinearGradient, QPainter, QPolygonF, QRadialGradient
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from main import APP_STYLE  # noqa: E402
import wordpop.ui.main_window as main_window  # noqa: E402
from wordpop.services.alignment import Word  # noqa: E402
from wordpop.utils.config_manager import DEFAULT_SETTINGS  # noqa: E402


def demo_background() -> "QPixmap":
    from PySide6.QtGui import QPixmap

    width, height = 540, 960
    pixmap = QPixmap(width, height)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    sky = QLinearGradient(0, 0, 0, height)
    sky.setColorAt(0.0, QColor("#9bb2c3"))
    sky.setColorAt(0.48, QColor("#d19a79"))
    sky.setColorAt(1.0, QColor("#18293a"))
    painter.fillRect(0, 0, width, height, sky)

    glow = QRadialGradient(QPointF(385, 390), 230)
    glow.setColorAt(0.0, QColor(255, 194, 133, 180))
    glow.setColorAt(1.0, QColor(255, 194, 133, 0))
    painter.fillRect(0, 160, width, 470, glow)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#f3c493"))
    painter.drawEllipse(QPointF(385, 390), 42, 42)

    painter.setBrush(QColor("#586b77"))
    painter.drawPolygon(QPolygonF([QPointF(0, 600), QPointF(125, 435), QPointF(280, 615), QPointF(430, 455), QPointF(540, 590), QPointF(540, 960), QPointF(0, 960)]))
    painter.setBrush(QColor("#293d4c"))
    painter.drawPolygon(QPolygonF([QPointF(0, 700), QPointF(165, 515), QPointF(320, 710), QPointF(470, 540), QPointF(540, 620), QPointF(540, 960), QPointF(0, 960)]))
    painter.setBrush(QColor("#142433"))
    painter.drawPolygon(QPolygonF([QPointF(0, 790), QPointF(150, 660), QPointF(285, 795), QPointF(430, 645), QPointF(540, 745), QPointF(540, 960), QPointF(0, 960)]))
    painter.end()
    return pixmap


def main() -> None:
    app = QApplication([])
    app.setApplicationName("WordPop Studio")
    app.setOrganizationName("WordPop Studio")

    # The offscreen screenshot run keeps app settings/logs inside ignored temp data.
    main_window.QStandardPaths.writableLocation = lambda *_args: str(ROOT / "temp" / "readme-appdata")

    if sys.platform == "win32":
        for name in ("segoeui.ttf", "segoeuib.ttf", "arial.ttf", "arialbd.ttf"):
            font_path = Path("C:/Windows/Fonts") / name
            if font_path.is_file():
                QFontDatabase.addApplicationFont(str(font_path))

    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    window = main_window.MainWindow()
    window.resize(1600, 1000)

    sample_words = [
        Word("Imagine", 0.00, 0.45),
        Word("looking", 0.45, 0.90),
        Word("Nara,", 0.90, 1.40),
        Word("Japan,", 1.40, 1.90),
        Word("fire", 1.90, 2.40),
    ]
    settings = dict(DEFAULT_SETTINGS)
    settings["uppercase"] = True
    window.settings_panel.blockSignals(True)
    window.settings_panel.set_values(settings)
    window.settings_panel.blockSignals(False)
    window.preview_card.preview._pixmap = demo_background()
    window.editor.set_words(sample_words)
    window.preview_card.preview.set_words(sample_words)
    window.preview_card.preview.set_style(window.settings_panel.style())
    window.preview_card.preview.set_index(2)
    window.media_info_label.setText("Demo_JapanStory.mp4  ·  1080 × 1920  ·  30 fps  ·  audio available")
    window.output_path.setText("output/Demo_JapanStory_WordPop.mp4")

    window.show()
    for _ in range(5):
        app.processEvents()
        time.sleep(0.04)

    (ROOT / "assets").mkdir(exist_ok=True)
    window.grab().save(str(ROOT / "assets" / "wordpop-studio-overview.png"))
    window.preview_card.preview.grab().save(str(ROOT / "assets" / "wordpop-caption-preview.png"))
    window.close()


if __name__ == "__main__":
    main()
