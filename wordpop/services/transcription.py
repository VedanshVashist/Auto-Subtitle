from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Iterator

from .alignment import Word, clamp_word_boundaries

logger = logging.getLogger(__name__)

MODEL_SIZES = {"tiny": "~75 MB", "base": "~145 MB", "small": "~484 MB", "medium": "~1.5 GB", "large-v3": "~3.1 GB"}


class TranscriptionCancelled(RuntimeError):
    pass


def transcribe_file(
    audio_path: Path,
    *,
    model_name: str = "base",
    language: str = "auto",
    cache_dir: Path,
    duration: float,
    progress: Callable[[int, str], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    prefer_gpu: bool = False,
) -> tuple[list[Word], str, str]:
    if not Path(audio_path).is_file():
        raise FileNotFoundError(f"Audio or video file not found: {audio_path}")
    if model_name not in MODEL_SIZES:
        raise ValueError(f"Unsupported model '{model_name}'. Choose one of {', '.join(MODEL_SIZES)}.")
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("faster-whisper is not installed. Run the included setup.bat first.") from exc

    cache_dir.mkdir(parents=True, exist_ok=True)
    gpu_active = False
    device, compute_type = ("cuda", "float16") if prefer_gpu else ("cpu", "int8")
    if progress:
        size = MODEL_SIZES[model_name]
        progress(2, f"Loading {model_name} model ({size}); first run downloads it to the local cache…")
    try:
        model = WhisperModel(model_name, device=device, compute_type=compute_type, download_root=str(cache_dir), cpu_threads=4)
        gpu_active = device == "cuda"
    except Exception as exc:
        if not prefer_gpu:
            raise RuntimeError(f"Could not load the {model_name} model: {exc}") from exc
        logger.warning("CUDA model setup failed; retrying on CPU: %s", exc)
        if progress:
            progress(3, f"GPU setup failed ({exc}); switching to CPU int8…")
        model = WhisperModel(model_name, device="cpu", compute_type="int8", download_root=str(cache_dir), cpu_threads=4)
        device, compute_type = "cpu", "int8"

    lang = None if language.casefold() in ("auto", "", "detect") else language
    segments, info = model.transcribe(
        str(audio_path),
        language=lang,
        word_timestamps=True,
        vad_filter=True,
        beam_size=3,
        condition_on_previous_text=True,
    )
    detected_language = getattr(info, "language", None) or language or "auto"
    words: list[Word] = []
    for segment in segments:
        if is_cancelled and is_cancelled():
            raise TranscriptionCancelled("Transcription cancelled.")
        segment_words = getattr(segment, "words", None) or []
        if segment_words:
            for item in segment_words:
                value = str(getattr(item, "word", "")).strip()
                start = float(getattr(item, "start", segment.start))
                end = float(getattr(item, "end", segment.end))
                confidence = getattr(item, "probability", None)
                if value and end > start:
                    words.append(Word(value, start, end, float(confidence) if confidence is not None else None, "aligned"))
        else:
            # This is an explicit fallback and is labeled as estimated for review.
            tokens = str(segment.text).split()
            span = max(0.01, float(segment.end) - float(segment.start))
            for index, token in enumerate(tokens):
                words.append(Word(token, float(segment.start) + span * index / len(tokens), float(segment.start) + span * (index + 1) / len(tokens), None, "estimated"))
        if progress and duration > 0:
            pct = min(98, max(4, round(float(segment.end) / duration * 95) + 3))
            progress(pct, f"Transcribed to {float(segment.end):.1f}s / {duration:.1f}s…")

    if not words:
        raise RuntimeError("No speech was recognized. Check the audio track or try another model.")
    words = clamp_word_boundaries(words, duration)
    engine = f"faster-whisper {model_name} ({device}/{compute_type})" + (" GPU" if gpu_active else " CPU")
    if progress:
        progress(100, f"Finished: {len(words)} words, language {detected_language}, {engine}.")
    return words, detected_language, engine
