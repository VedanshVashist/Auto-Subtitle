import pytest

from wordpop.utils.config_manager import ConfigManager
from wordpop.utils.ffmpeg_utils import unique_output_path


def test_config_and_builtin_presets_load_save_and_reload(tmp_path):
    shipped = tmp_path / "defaults.json"
    shipped.write_text('{"Classic WordPop":{"mode":"single","active_color":"#FFD400"}}', encoding="utf-8")
    manager = ConfigManager(tmp_path / "settings.json", tmp_path / "custom.json", shipped)
    assert manager.settings["preset"] == "Classic WordPop"
    assert manager.apply_preset("Classic WordPop")["active_color"] == "#FFD400"
    manager.save_preset("Creator", {"mode": "phrase", "font_size": 72})
    manager.save({"font_size": 72})
    reloaded = ConfigManager(tmp_path / "settings.json", tmp_path / "custom.json", shipped)
    assert reloaded.settings["font_size"] == 72
    assert reloaded.presets["Creator"]["mode"] == "phrase"
    reloaded.rename_preset("Creator", "My captions")
    reloaded.delete_preset("My captions")
    with pytest.raises(ValueError, match="cannot be renamed"):
        reloaded.rename_preset("Classic WordPop", "Something else")
    with pytest.raises(ValueError, match="cannot be deleted"):
        reloaded.delete_preset("Classic WordPop")


def test_output_filename_is_unique_and_does_not_overwrite(tmp_path):
    existing = tmp_path / "video.mp4"
    existing.touch()
    second = unique_output_path(tmp_path, "video")
    assert second.name == "video_2.mp4"
    assert existing.exists()


def test_missing_input_is_reported_before_render(tmp_path):
    from wordpop.services.video_processor import render_video
    from wordpop.services.subtitle_renderer import SubtitleStyle

    with pytest.raises(FileNotFoundError, match="Source video not found"):
        render_video(tmp_path / "missing.mp4", tmp_path / "out.mp4", [], SubtitleStyle())


def test_existing_output_is_not_overwritten_without_explicit_confirmation(tmp_path):
    from wordpop.services.video_processor import render_video
    from wordpop.services.subtitle_renderer import SubtitleStyle

    source = tmp_path / "source.mp4"
    output = tmp_path / "out.mp4"
    source.write_bytes(b"source marker")
    output.write_bytes(b"keep this file")
    with pytest.raises(FileExistsError, match="Output already exists"):
        render_video(source, output, [], SubtitleStyle())
    assert output.read_bytes() == b"keep this file"
