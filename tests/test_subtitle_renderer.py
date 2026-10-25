import pytest
import re

from wordpop.services.alignment import Word
from wordpop.services.subtitle_renderer import SubtitleStyle, animation_progress, font_fallback, render_ass, safe_position


def test_safe_position_respects_safe_margins():
    x, y = safe_position(1080, 1920, 62, margin_x=8, margin_y=5)
    assert x == 540
    assert y == 1190
    assert safe_position(100, 100, 0, margin_y=20)[1] == 20


def test_animation_is_smooth_monotonic_and_settles_at_one():
    values = [animation_progress(t, 130, 0.8) for t in (0, 20, 60, 100, 130, 160)]
    assert values[0] == pytest.approx(0.8)
    assert values[-1] == 1
    assert values == sorted(values)


def test_font_fallback_uses_requested_then_sensible_system_family():
    assert font_fallback("arial", ["Arial", "Segoe UI"]) == "Arial"
    assert font_fallback("Missing Font", ["Segoe UI", "Noto Sans"]) == "Segoe UI"
    assert font_fallback("Missing Font", []) == "Arial"


def test_ass_has_word_times_yellow_fill_true_stroke_and_pop():
    ass = render_ass([Word("hello", 1.25, 1.6)], 1080, 1920, SubtitleStyle())
    assert "Dialogue: 0,0:00:01.25,0:00:01.60" in ass
    assert "&H0000D4FF&" in ass
    assert "\\bord6.22" in ass
    assert "\\t(0,130,0.35,\\fscx" in ass
    assert "\\clip(86,96,994,1824)" in ass


def test_phrase_mode_never_displays_future_words():
    words = [Word("first", 0.0, 0.2), Word("second", 0.2, 0.5), Word("future", 0.5, 0.8)]
    ass = render_ass(words, 1080, 1920, SubtitleStyle(mode="phrase", phrase_length=3))
    events = [line for line in ass.splitlines() if line.startswith("Dialogue:")]
    visible_first = re.sub(r"\{.*?\}", "", events[0])
    visible_second = re.sub(r"\{.*?\}", "", events[1])
    assert "first" in visible_first and "second" not in visible_first
    assert "first second" in visible_second and "future" not in visible_second


def test_uppercase_changes_rendered_caption_text_only():
    word = Word("A quiet story", 0.0, 0.7)
    ass = render_ass([word], 1080, 1920, SubtitleStyle(uppercase=True))
    assert "A QUIET STORY" in ass
    assert word.text == "A quiet story"


def test_long_tokens_are_scaled_to_safe_width():
    ass = render_ass([Word("extraordinarilylongword", 0, 1)], 720, 1280, SubtitleStyle())
    assert "\\fscx" in ass
