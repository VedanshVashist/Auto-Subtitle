from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from wordpop.ui.main_window import MainWindow


APP_STYLE = """
QWidget { background: #11151d; color: #e8edf5; font-family: 'Segoe UI', 'Arial'; font-size: 10pt; }
QMainWindow { background: #0d1118; }
QLabel#brandTitle { font-size: 23pt; font-weight: 750; color: #f4f7fb; }
QLabel#eyebrow { color: #8795aa; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }
QLabel#mutedText { color: #8591a2; font-size: 9pt; }
QLabel#mediaInfo, QLabel#statusText { color: #b6c2d2; font-size: 9pt; }
QGroupBox { border: 1px solid #2b3443; border-radius: 9px; margin-top: 11px; padding: 12px 10px 10px; font-weight: 650; color: #dfe7f1; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #9cabc0; }
QPushButton { background: #202735; border: 1px solid #344052; border-radius: 7px; padding: 8px 12px; color: #edf2f8; font-weight: 600; }
QPushButton:hover { background: #2a3545; border-color: #53647a; }
QPushButton:disabled { color: #657184; background: #1b212b; }
QPushButton#primaryButton { background: #6655df; border-color: #7969ee; color: white; padding: 10px 15px; }
QPushButton#primaryButton:hover { background: #7667ec; }
QPushButton#successButton { background: #138b78; border-color: #1ca590; color: white; padding: 10px 15px; }
QPushButton#successButton:hover { background: #19a18b; }
QPushButton#dangerButton { background: #42262b; border-color: #704047; color: #f6b7bd; }
QPushButton#ghostButton { background: #171e28; border-color: #303c4d; padding: 6px 10px; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: #171d27; border: 1px solid #303a49; border-radius: 6px; padding: 6px 8px; selection-background-color: #6655df; }
QComboBox QAbstractItemView { background: #1b222e; selection-background-color: #6655df; border: 1px solid #354256; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QSlider::groove:horizontal { height: 4px; background: #303949; border-radius: 2px; }
QSlider::handle:horizontal { background: #8a7cff; width: 14px; margin: -5px 0; border-radius: 7px; }
QProgressBar { background: #191f29; border: 1px solid #303a49; border-radius: 6px; height: 12px; text-align: center; color: transparent; }
QProgressBar::chunk { background: #8270ff; border-radius: 5px; }
QTableWidget { background: #121821; alternate-background-color: #171e28; border: 1px solid #2a3442; border-radius: 7px; gridline-color: #252f3d; selection-background-color: #413b75; selection-color: white; }
QHeaderView::section { background: #1c2430; color: #aeb9ca; border: 0; border-bottom: 1px solid #303948; padding: 7px; font-weight: 650; }
QScrollBar:vertical { background: #111720; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #344052; border-radius: 5px; min-height: 30px; }
QSplitter::handle { background: #0d1118; width: 8px; }
QStatusBar { color: #718097; border-top: 1px solid #242d3a; }
"""


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("WordPop Studio")
    app.setOrganizationName("WordPop Studio")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    startup_path = sys.argv[1] if len(sys.argv) > 1 else None
    window = MainWindow(startup_path)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
