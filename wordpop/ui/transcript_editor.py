from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QHBoxLayout, QLabel

from ..services.alignment import Word, validate_words


class TranscriptEditor(QWidget):
    word_selected = Signal(int)
    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", "Word", "Start (s)", "End (s)"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(self.changed.emit)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.delete_button = QPushButton("Delete selected")
        self.delete_button.setObjectName("ghostButton")
        self.delete_button.clicked.connect(self.delete_selected)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        title = QLabel("TRANSCRIPT")
        title.setObjectName("eyebrow")
        self.count_label = QLabel("No words yet")
        self.count_label.setObjectName("mutedText")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.count_label)
        header.addWidget(self.delete_button)
        layout.addLayout(header)
        layout.addWidget(self.table, 1)

    def set_words(self, words: Sequence[Word]) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(words))
        for row, word in enumerate(words):
            values = [str(row + 1), word.text, f"{word.start:.3f}", f"{word.end:.3f}"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if column in (2, 3) or column == 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)
        self.table.blockSignals(False)
        self.count_label.setText(f"{len(words)} words · edit text or timestamps")

    def get_words(self, duration: float | None = None) -> list[Word]:
        words: list[Word] = []
        for row in range(self.table.rowCount()):
            try:
                words.append(Word(
                    text=self.table.item(row, 1).text().strip(),
                    start=float(self.table.item(row, 2).text()),
                    end=float(self.table.item(row, 3).text()),
                    timing="edited",
                ))
            except (AttributeError, ValueError) as exc:
                raise ValueError(f"Row {row + 1} needs a word and numeric start/end seconds.") from exc
        return validate_words(words, duration)

    def delete_selected(self) -> None:
        rows = sorted({item.row() for item in self.table.selectedItems()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)
        if rows:
            self._renumber()
            self.count_label.setText(f"{self.table.rowCount()} words · edit text or timestamps")
            self.changed.emit()

    def _renumber(self) -> None:
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setText(str(row + 1))

    def _selection_changed(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if selected:
            self.word_selected.emit(selected[0].row())
