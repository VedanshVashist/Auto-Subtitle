from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS: dict[str, Any] = {
    "font_family": "Arial",
    "font_size": 64,
    "text_color": "#FFFFFF",
    "active_color": "#FFD400",
    "outline_color": "#000000",
    "outline_width": 3.5,
    "shadow": True,
    "pop_enabled": True,
    "animation_ms": 130,
    "animation_intensity": 80,
    "position_percent": 62,
    "margin_x": 8,
    "margin_y": 5,
    "mode": "single",
    "phrase_length": 4,
    "uppercase": False,
    "language": "auto",
    "model": "base",
    "resolution": "Original",
    "crf": 20,
    "preset": "Classic WordPop",
}


class ConfigManager:
    def __init__(self, settings_path: Path, presets_path: Path | None = None, defaults_presets_path: Path | None = None) -> None:
        self.settings_path = Path(settings_path)
        self.presets_path = Path(presets_path) if presets_path else None
        self.defaults_presets_path = Path(defaults_presets_path) if defaults_presets_path else None
        self.presets: dict[str, dict[str, Any]] = {}
        self._builtin_names: set[str] = set()
        self.settings = deepcopy(DEFAULT_SETTINGS)
        self._load_presets()
        self.load()

    def _load_presets(self) -> None:
        if self.defaults_presets_path and self.defaults_presets_path.exists():
            try:
                payload = json.loads(self.defaults_presets_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    self.presets = {str(k): dict(v) for k, v in payload.items() if isinstance(v, dict)}
                    self._builtin_names = set(self.presets)
            except (OSError, json.JSONDecodeError):
                self.presets = {}
        if self.presets_path and self.presets_path.exists():
            try:
                payload = json.loads(self.presets_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    self.presets.update({str(k): dict(v) for k, v in payload.items() if isinstance(v, dict)})
            except (OSError, json.JSONDecodeError):
                self.presets = {}
        self.presets.setdefault("Classic WordPop", {
            "mode": "single", "text_color": "#FFFFFF", "active_color": "#FFD400",
            "outline_color": "#000000", "outline_width": 3.5, "shadow": True,
            "pop_enabled": True, "animation_ms": 130, "animation_intensity": 80,
            "position_percent": 62, "phrase_length": 4,
        })

    def load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self.settings.update(data)
        except (OSError, json.JSONDecodeError):
            pass
        return deepcopy(self.settings)

    def save(self, settings: dict[str, Any] | None = None) -> None:
        if settings is not None:
            self.settings.update(settings)
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(json.dumps(self.settings, indent=2, ensure_ascii=False), encoding="utf-8")

    def apply_preset(self, name: str) -> dict[str, Any]:
        if name not in self.presets:
            raise KeyError(f"Unknown preset: {name}")
        self.settings.update(self.presets[name])
        self.settings["preset"] = name
        return deepcopy(self.settings)

    def save_preset(self, name: str, settings: dict[str, Any]) -> None:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Preset name cannot be empty.")
        self.presets[clean_name] = deepcopy(settings)
        self._save_presets()

    def rename_preset(self, old_name: str, new_name: str) -> None:
        clean_name = new_name.strip()
        if old_name not in self.presets:
            raise KeyError(f"Unknown preset: {old_name}")
        if old_name in self._builtin_names:
            raise ValueError("Built-in presets cannot be renamed; save a custom copy instead.")
        if not clean_name:
            raise ValueError("Preset name cannot be empty.")
        self.presets[clean_name] = self.presets.pop(old_name)
        self._save_presets()

    def delete_preset(self, name: str) -> None:
        if name not in self.presets:
            raise KeyError(f"Unknown preset: {name}")
        if name in self._builtin_names:
            raise ValueError("Built-in presets cannot be deleted.")
        del self.presets[name]
        self._save_presets()

    def _save_presets(self) -> None:
        if not self.presets_path:
            return
        self.presets_path.parent.mkdir(parents=True, exist_ok=True)
        self.presets_path.write_text(json.dumps(self.presets, indent=2, ensure_ascii=False), encoding="utf-8")
