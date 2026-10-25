from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFontComboBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSlider, QSpinBox,
    QVBoxLayout, QWidget,
)

from ..services.subtitle_renderer import SubtitleStyle


class ColorButton(QPushButton):
    color_changed = Signal(str)

    def __init__(self, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = color
        self.setMinimumWidth(112)
        self.clicked.connect(self._choose)
        self._refresh()

    @property
    def color(self) -> str:
        return self._color

    def set_color(self, color: str) -> None:
        if QColor(color).isValid():
            self._color = QColor(color).name().upper()
            self._refresh()

    def _refresh(self) -> None:
        fg = "#10141B" if QColor(self._color).lightness() > 155 else "#FFFFFF"
        self.setText(self._color)
        self.setStyleSheet(f"background: {self._color}; color: {fg}; border: 1px solid #394252; border-radius: 6px; padding: 6px 10px;")

    def _choose(self) -> None:
        color = QColorDialog.getColor(QColor(self._color), self, "Choose subtitle color")
        if color.isValid():
            self.set_color(color.name())
            self.color_changed.emit(self._color)


class SettingsPanel(QWidget):
    settings_changed = Signal(dict)
    preset_selected = Signal(str)
    save_preset_requested = Signal()
    rename_preset_requested = Signal(str)
    delete_preset_requested = Signal(str)

    def __init__(self, presets: list[str], initial: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._building = True
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(0, 0, 0, 4)
        root.setSpacing(14)

        preset_group = QGroupBox("Preset")
        preset_layout = QVBoxLayout(preset_group)
        preset_row = QHBoxLayout()
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(presets)
        self.preset_combo.setCurrentText(str(initial.get("preset", "Classic WordPop")))
        self.save_preset_button = QPushButton("Save as")
        self.rename_preset_button = QPushButton("Rename")
        self.delete_preset_button = QPushButton("Delete")
        self.save_preset_button.setObjectName("ghostButton")
        self.rename_preset_button.setObjectName("ghostButton")
        self.delete_preset_button.setObjectName("ghostButton")
        preset_row.addWidget(self.preset_combo, 1)
        preset_row.addWidget(self.save_preset_button)
        preset_layout.addLayout(preset_row)
        manage_row = QHBoxLayout()
        manage_row.addStretch()
        manage_row.addWidget(self.rename_preset_button)
        manage_row.addWidget(self.delete_preset_button)
        preset_layout.addLayout(manage_row)
        root.addWidget(preset_group)

        style_group = QGroupBox("Subtitle style")
        form = QFormLayout(style_group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.font = QFontComboBox()
        self.font.setCurrentFont(self.font.currentFont())
        self.font.setCurrentText(str(initial.get("font_family", "Arial")))
        self.font_size = QSpinBox()
        self.font_size.setRange(24, 180)
        self.font_size.setSuffix(" px at 1080p")
        self.outline_width = QDoubleSpinBox()
        self.outline_width.setRange(0, 12)
        self.outline_width.setSingleStep(0.5)
        self.outline_width.setSuffix(" px")
        self.text_color = ColorButton(str(initial.get("text_color", "#FFFFFF")))
        self.active_color = ColorButton(str(initial.get("active_color", "#FFD400")))
        self.outline_color = ColorButton(str(initial.get("outline_color", "#000000")))
        self.shadow = QCheckBox("Soft text shadow")
        self.uppercase = QCheckBox("Display captions in ALL CAPS")
        self.pop = QCheckBox("Pop-up on each word")
        self.animation_ms = QSpinBox()
        self.animation_ms.setRange(0, 500)
        self.animation_ms.setSuffix(" ms")
        self.intensity = QSpinBox()
        self.intensity.setRange(50, 100)
        self.intensity.setSuffix("% start size")
        self.position = QSlider()
        self.position.setOrientation(Qt.Orientation.Horizontal)
        self.position.setRange(40, 85)
        self.position_label = QLabel("62% from top")
        position_row = QHBoxLayout()
        position_row.addWidget(self.position, 1)
        position_row.addWidget(self.position_label)
        position_wrap = QWidget()
        position_wrap.setLayout(position_row)
        self.margin_x = QSpinBox()
        self.margin_x.setRange(0, 25)
        self.margin_x.setSuffix("% each side")
        self.margin_y = QSpinBox()
        self.margin_y.setRange(0, 25)
        self.margin_y.setSuffix("% safe area")
        self.mode = QComboBox()
        self.mode.addItem("Single active word", "single")
        self.mode.addItem("Growing phrase · active word highlighted", "phrase")
        self.phrase_length = QSpinBox()
        self.phrase_length.setRange(2, 8)
        self.phrase_length.setSuffix(" words maximum")
        form.addRow("Font", self.font)
        form.addRow("Text size", self.font_size)
        form.addRow("Text color", self.text_color)
        form.addRow("Active word", self.active_color)
        form.addRow("Stroke color", self.outline_color)
        form.addRow("Stroke thickness", self.outline_width)
        form.addRow("Effects", self.shadow)
        form.addRow("Capitalization", self.uppercase)
        form.addRow("Animation", self.pop)
        form.addRow("Animation length", self.animation_ms)
        form.addRow("Start scale", self.intensity)
        form.addRow("Vertical position", position_wrap)
        form.addRow("Horizontal safe margin", self.margin_x)
        form.addRow("Vertical safe margin", self.margin_y)
        form.addRow("Display mode", self.mode)
        form.addRow("Phrase length", self.phrase_length)
        root.addWidget(style_group)

        speech_group = QGroupBox("Transcription")
        speech_form = QFormLayout(speech_group)
        self.language = QComboBox()
        for text, code in (("Automatic detection", "auto"), ("English", "en"), ("Hindi", "hi"), ("Hinglish · automatic", "auto")):
            self.language.addItem(text, code)
        self.model = QComboBox()
        for name, size in (("tiny", "~75 MB · fastest"), ("base", "~145 MB · recommended"), ("small", "~484 MB · more accurate"), ("medium", "~1.5 GB"), ("large-v3", "~3.1 GB")):
            self.model.addItem(f"{name}  ·  {size}", name)
        speech_form.addRow("Language", self.language)
        speech_form.addRow("Whisper model", self.model)
        root.addWidget(speech_group)
        root.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._widgets = (
            self.font, self.font_size, self.text_color, self.active_color, self.outline_color,
            self.outline_width, self.shadow, self.uppercase, self.pop, self.animation_ms, self.intensity,
            self.position, self.margin_x, self.margin_y, self.mode, self.phrase_length,
            self.language, self.model,
        )
        self._set_initial(initial)
        for widget in self._widgets:
            if isinstance(widget, QFontComboBox):
                widget.currentFontChanged.connect(self._emit)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._emit)
            elif isinstance(widget, QCheckBox):
                widget.toggled.connect(self._emit)
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox, QSlider)):
                widget.valueChanged.connect(self._emit)
        for button in (self.text_color, self.active_color, self.outline_color):
            button.color_changed.connect(self._emit)
        self.preset_combo.currentTextChanged.connect(self.preset_selected.emit)
        self.save_preset_button.clicked.connect(self.save_preset_requested.emit)
        self.rename_preset_button.clicked.connect(lambda: self.rename_preset_requested.emit(self.preset_combo.currentText()))
        self.delete_preset_button.clicked.connect(lambda: self.delete_preset_requested.emit(self.preset_combo.currentText()))
        self._building = False
        self._emit()

    def _set_initial(self, values: dict[str, Any]) -> None:
        self.font_size.setValue(int(values.get("font_size", 64)))
        self.outline_width.setValue(float(values.get("outline_width", 3.5)))
        self.shadow.setChecked(bool(values.get("shadow", True)))
        self.uppercase.setChecked(bool(values.get("uppercase", False)))
        self.pop.setChecked(bool(values.get("pop_enabled", True)))
        self.animation_ms.setValue(int(values.get("animation_ms", 130)))
        self.intensity.setValue(int(values.get("animation_intensity", 80)))
        self.position.setValue(int(values.get("position_percent", 62)))
        self.margin_x.setValue(int(values.get("margin_x", 8)))
        self.margin_y.setValue(int(values.get("margin_y", 5)))
        self.phrase_length.setValue(int(values.get("phrase_length", 4)))
        self.mode.setCurrentIndex(max(0, self.mode.findData(values.get("mode", "single"))))
        self.language.setCurrentIndex(max(0, self.language.findData(values.get("language", "auto"))))
        self.model.setCurrentIndex(max(0, self.model.findData(values.get("model", "base"))))
        self.text_color.set_color(str(values.get("text_color", "#FFFFFF")))
        self.active_color.set_color(str(values.get("active_color", "#FFD400")))
        self.outline_color.set_color(str(values.get("outline_color", "#000000")))
        family = str(values.get("font_family", "Arial"))
        if self.font.findText(family) >= 0:
            self.font.setCurrentText(family)
        self.position_label.setText(f"{self.position.value()}% from top")

    def set_values(self, values: dict[str, Any]) -> None:
        self._building = True
        self._set_initial(values)
        self._building = False
        self._emit()

    def refresh_presets(self, names: list[str], selected: str | None = None) -> None:
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItems(names)
        if selected:
            self.preset_combo.setCurrentText(selected)
        self.preset_combo.blockSignals(False)

    def values(self) -> dict[str, Any]:
        return {
            "font_family": self.font.currentFont().family(),
            "font_size": self.font_size.value(),
            "text_color": self.text_color.color,
            "active_color": self.active_color.color,
            "outline_color": self.outline_color.color,
            "outline_width": self.outline_width.value(),
            "shadow": self.shadow.isChecked(),
            "uppercase": self.uppercase.isChecked(),
            "pop_enabled": self.pop.isChecked(),
            "animation_ms": self.animation_ms.value(),
            "animation_intensity": self.intensity.value(),
            "position_percent": self.position.value(),
            "margin_x": self.margin_x.value(),
            "margin_y": self.margin_y.value(),
            "mode": self.mode.currentData(),
            "phrase_length": self.phrase_length.value(),
            "language": self.language.currentData(),
            "model": self.model.currentData(),
            "preset": self.preset_combo.currentText(),
        }

    def style(self) -> SubtitleStyle:
        values = {key: value for key, value in self.values().items() if key not in {"language", "model", "preset"}}
        values["font_family"] = self.font.currentFont().family()
        return SubtitleStyle(**values)

    def _emit(self, *args) -> None:
        self.position_label.setText(f"{self.position.value()}% from top")
        if not self._building:
            self.settings_changed.emit(self.values())
