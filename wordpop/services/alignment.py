from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class Word:
    text: str
    start: float
    end: float
    confidence: float | None = None
    timing: str = "aligned"

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "Word":
        return cls(
            text=str(data.get("text", "")).strip(),
            start=parse_timestamp(data.get("start", 0)),
            end=parse_timestamp(data.get("end", 0)),
            confidence=float(data["confidence"]) if data.get("confidence") is not None else None,
            timing=str(data.get("timing", "aligned")),
        )


def parse_timestamp(value: str | float | int) -> float:
    """Parse seconds or HH:MM:SS[.mmm] into seconds."""
    if isinstance(value, (int, float)):
        result = float(value)
    else:
        text = str(value).strip()
        if re.fullmatch(r"\d+(?:\.\d+)?", text):
            result = float(text)
        else:
            parts = text.split(":")
            if len(parts) != 3 or not re.fullmatch(r"\d+(?:\.\d+)?", parts[2]):
                raise ValueError(f"Invalid timestamp: {value}")
            hours, minutes = int(parts[0]), int(parts[1])
            seconds = float(parts[2])
            if minutes >= 60 or seconds >= 60:
                raise ValueError(f"Invalid timestamp: {value}")
            result = hours * 3600 + minutes * 60 + seconds
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"Invalid timestamp: {value}")
    return result


def validate_words(words: Iterable[Word | dict[str, object]], duration: float | None = None) -> list[Word]:
    validated: list[Word] = []
    for index, raw in enumerate(words):
        word = raw if isinstance(raw, Word) else Word.from_dict(raw)
        if not word.text:
            raise ValueError(f"Word {index + 1} has empty text.")
        if not math.isfinite(word.start) or not math.isfinite(word.end):
            raise ValueError(f"Word {index + 1} has a non-finite timestamp.")
        if word.start < 0 or word.end <= word.start:
            raise ValueError(f"Word {index + 1} must have start >= 0 and end > start.")
        if duration is not None and (word.start > duration or word.end > duration + 0.05):
            raise ValueError(f"Word {index + 1} extends past the video duration ({duration:.2f}s).")
        if validated and word.start + 0.05 < validated[-1].start:
            raise ValueError(f"Word {index + 1} starts before the previous word.")
        validated.append(word)
    return validated


def clamp_word_boundaries(words: Iterable[Word], duration: float) -> list[Word]:
    """Keep aligned times while clipping model rounding to the media duration."""
    result: list[Word] = []
    for word in words:
        start = max(0.0, min(float(word.start), max(0.0, duration - 0.01)))
        end = max(start + 0.01, min(float(word.end), duration))
        result.append(Word(word.text, start, end, word.confidence, word.timing))
    return result


def non_overlapping_words(words: Iterable[Word]) -> list[Word]:
    """Shorten simultaneous model word spans so exactly one active caption is visible."""
    checked = validate_words(words)
    result: list[Word] = []
    for index, word in enumerate(checked):
        end = min(word.end, checked[index + 1].start) if index + 1 < len(checked) else word.end
        if end > word.start:
            result.append(Word(word.text, word.start, end, word.confidence, word.timing))
    return result


def save_transcript(path: Path, words: Iterable[Word], *, source_video: str = "", language: str = "auto") -> None:
    checked = validate_words(words)
    payload = {
        "format": "wordpop-transcript-v1",
        "source_video": source_video,
        "language": language,
        "words": [asdict(word) for word in checked],
    }
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_transcript(path: Path, duration: float | None = None) -> tuple[list[Word], str]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_words = payload.get("words") if isinstance(payload, dict) else payload
    if not isinstance(raw_words, list):
        raise ValueError("Transcript JSON must contain a words list.")
    words = validate_words(raw_words, duration)
    return words, str(payload.get("language", "auto")) if isinstance(payload, dict) else "auto"
