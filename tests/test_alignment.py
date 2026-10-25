import json

import pytest

from wordpop.services.alignment import Word, load_transcript, non_overlapping_words, parse_timestamp, save_transcript, validate_words


def test_timestamp_parsing_accepts_seconds_and_clock_format():
    assert parse_timestamp("00:01:02.250") == pytest.approx(62.25)
    assert parse_timestamp("3.5") == 3.5


@pytest.mark.parametrize("value", ["", "1:90:00", "nan", "-1", "00:00:61.0"])
def test_timestamp_parser_rejects_invalid_input(value):
    with pytest.raises(ValueError):
        parse_timestamp(value)


def test_word_timing_boundaries_are_validated():
    words = validate_words([Word("one", 0, 0.3), Word("two", 0.31, 0.7)], duration=1)
    assert words[-1].end <= 1
    with pytest.raises(ValueError, match="end > start"):
        validate_words([Word("bad", 0.5, 0.5)])
    with pytest.raises(ValueError, match="duration"):
        validate_words([Word("late", 1.1, 1.4)], duration=1)
    with pytest.raises(ValueError, match="previous word"):
        validate_words([Word("one", 0.6, 0.7), Word("two", 0.2, 0.4)])


def test_overlapping_model_word_spans_are_trimmed_for_single_word_display():
    words = non_overlapping_words([Word("one", 0.0, 0.5), Word("two", 0.4, 0.8)])
    assert words[0].end == pytest.approx(0.4)
    assert words[1].start == pytest.approx(0.4)


def test_transcript_saves_and_reloads(tmp_path):
    path = tmp_path / "sample.wordpop.json"
    original = [Word("Hello", 0.1, 0.4), Word("東京", 0.5, 1.0, timing="estimated")]
    save_transcript(path, original, source_video="source.mp4", language="en")
    restored, language = load_transcript(path, duration=1.1)
    assert language == "en"
    assert [(word.text, word.start, word.end, word.timing) for word in restored] == [
        ("Hello", 0.1, 0.4, "aligned"), ("東京", 0.5, 1.0, "estimated")
    ]
    assert json.loads(path.read_text(encoding="utf-8"))["format"] == "wordpop-transcript-v1"


def test_load_transcript_rejects_missing_word_list(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"language":"en"}', encoding="utf-8")
    with pytest.raises(ValueError, match="words list"):
        load_transcript(path)
