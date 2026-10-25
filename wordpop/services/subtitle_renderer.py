from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Sequence

from .alignment import Word, non_overlapping_words


@dataclass(frozen=True)
class SubtitleStyle:
    font_family: str = "Arial"
    font_size: int = 64
    text_color: str = "#FFFFFF"
    active_color: str = "#FFD400"
    outline_color: str = "#000000"
    outline_width: float = 3.5
    shadow: bool = True
    pop_enabled: bool = True
    animation_ms: int = 130
    animation_intensity: int = 80
    position_percent: int = 62
    margin_x: int = 8
    margin_y: int = 5
    mode: str = "single"
    phrase_length: int = 4
    uppercase: bool = False


def animation_progress(elapsed_ms: float, duration_ms: float = 130, intensity: float = 0.8) -> float:
    """Ease from the configured starting scale to 1 without an overshoot."""
    if duration_ms <= 0 or elapsed_ms >= duration_ms:
        return 1.0
    if elapsed_ms <= 0:
        return max(0.1, min(1.0, intensity))
    t = max(0.0, min(1.0, elapsed_ms / duration_ms))
    ease = 1.0 - (1.0 - t) ** 3
    start = max(0.1, min(1.0, intensity))
    return start + (1.0 - start) * ease


def safe_position(width: int, height: int, position_percent: int, margin_x: int = 8, margin_y: int = 5) -> tuple[int, int]:
    """Return a centered caption anchor constrained to percentage safe margins."""
    if width <= 0 or height <= 0:
        raise ValueError("Canvas width and height must be positive.")
    mx = max(0, min(40, int(margin_x))) / 100
    my = max(0, min(40, int(margin_y))) / 100
    x = round(width / 2)
    margin_y_percent = my * 100
    y = round(height * max(margin_y_percent, min(100 - margin_y_percent, int(position_percent))) / 100)
    x = max(round(width * mx), min(width - round(width * mx), x))
    return x, y


def font_fallback(requested: str, available: Sequence[str]) -> str:
    names = {item.casefold(): item for item in available}
    if requested.casefold() in names:
        return names[requested.casefold()]
    for fallback in ("Arial", "Aptos", "Segoe UI", "DejaVu Sans", "Liberation Sans"):
        if fallback.casefold() in names:
            return names[fallback.casefold()]
    return available[0] if available else "Arial"


def _ass_color(color: str) -> str:
    match = re.fullmatch(r"#([0-9a-fA-F]{6})", color.strip())
    if not match:
        raise ValueError(f"Color must be a #RRGGBB value: {color}")
    rgb = match.group(1)
    return f"&H00{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}&"


def _ass_time(seconds: float) -> str:
    ticks = max(0, round(seconds * 100))
    hours, rem = divmod(ticks, 360000)
    minutes, rem = divmod(rem, 6000)
    centiseconds = rem % 100
    secs = rem // 100
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def _escape_ass(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", " ").strip()


def _phrase_start(words: list[Word], index: int, maximum: int) -> int:
    start = index
    while start > 0 and index - start + 1 < maximum:
        previous = words[start - 1]
        current = words[start]
        if re.search(r"[.!?]$", previous.text) or current.start - previous.end > 0.65:
            break
        start -= 1
    return start


def render_ass(words: Sequence[Word], width: int, height: int, style: SubtitleStyle, *, reference_height: int = 1080) -> str:
    checked = non_overlapping_words(words)
    if width <= 0 or height <= 0 or reference_height <= 0:
        raise ValueError("Video dimensions and reference height must be positive.")
    if not checked:
        raise ValueError("Transcript is empty.")
    x, y = safe_position(width, height, style.position_percent, style.margin_x, style.margin_y)
    scale = height / reference_height
    font_size = max(8, round(style.font_size * scale))
    outline = max(0.1, style.outline_width * scale)
    shadow = max(0, round((1.2 if style.shadow else 0) * scale))
    intensity = max(10, min(100, style.animation_intensity))
    animation_ms = max(0, min(1000, style.animation_ms))
    base_color = _ass_color(style.text_color)
    active_color = _ass_color(style.active_color)
    outline_color = _ass_color(style.outline_color)
    font_name = style.font_family.replace(",", "") or "Arial"
    events: list[str] = []
    phrase_size = max(1, min(8, style.phrase_length))
    for index, word in enumerate(checked):
        display_word = word.text.upper() if style.uppercase else word.text
        if style.mode == "phrase":
            first = _phrase_start(checked, index, phrase_size)
            before = " ".join(_escape_ass(item.text.upper() if style.uppercase else item.text) for item in checked[first:index])
            current = _escape_ass(display_word)
            prefix = f"{before} " if before else ""
        else:
            prefix, current = "", _escape_ass(display_word)
        phrase_text = f"{prefix}{current}"
        safe_width = max(20, width * (1 - 2 * max(0, min(40, style.margin_x)) / 100))
        # A conservative estimate keeps unusually long words inside the safe area while
        # leaving glyph shaping to the system-installed font used by libass.
        estimated_width = max(1, len(phrase_text) * font_size * 0.62)
        target_scale = max(35, min(100, round(safe_width / estimated_width * 100)))
        anim_span = min(animation_ms, max(0, round((word.end - word.start) * 1000)))
        start_scale = round(target_scale * intensity / 100) if style.pop_enabled else target_scale
        start_y_scale = intensity if style.pop_enabled else 100
        anim = f"\\fscx{start_scale}\\fscy{start_y_scale}"
        if style.pop_enabled and anim_span > 0:
            anim += f"\\t(0,{anim_span},0.35,\\fscx{target_scale}\\fscy100)"
        tags = (
            f"{{\\an5\\pos({x},{y})\\bord{outline:.2f}\\shad{shadow}"
            f"\\3c{outline_color}\\1c{base_color}\\fn{font_name}\\fs{font_size}\\fscx{target_scale}"
            f"\\q2\\clip({round(width * style.margin_x / 100)},{round(height * style.margin_y / 100)},"
            f"{width - round(width * style.margin_x / 100)},{height - round(height * style.margin_y / 100)})}}"
        )
        line = tags
        if prefix:
            line += f"{{\\1c{base_color}}}{prefix}"
        line += f"{{\\1c{active_color}{anim}}}{current}"
        events.append(f"Dialogue: 0,{_ass_time(word.start)},{_ass_time(word.end)},WordPop,,0,0,0,,{line}")

    header = f"""[Script Info]
; WordPop Studio generated captions. Colors are actual text fills with a stroked outline.
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: WordPop,{font_name},{font_size},{base_color},{base_color},{outline_color},&H80000000&,1,0,0,0,100,100,0,0,1,{outline:.2f},{shadow},5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return header + "\n".join(events) + "\n"
