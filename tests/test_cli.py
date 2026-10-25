"""Unit tests for cli.py asset discovery, fallback mechanisms, and validation."""
from pathlib import Path
import pytest
from cli import (
    discover_assets,
    choose_default_assets,
    sort_candidates,
    is_explicit_none,
    parse_args,
    get_default_output_filename,
    main,
    PREFERRED_IMAGES,
    PREFERRED_GIFS,
    PREFERRED_AUDIO,
    BASE_DIR,
    ASSETS_DIR,
)


def test_discover_assets():
    images, gifs, audio = discover_assets(ASSETS_DIR)
    # Check that fonts are excluded
    for p in images + gifs + audio:
        assert "fonts" not in p.parts
        assert not p.name.startswith(".")

    assert any(p.suffix.lower() in [".jpg", ".png", ".webp"] for p in images)
    assert any(p.suffix.lower() == ".gif" for p in gifs)
    assert any(p.suffix.lower() in [".mpeg", ".mp3", ".wav"] for p in audio)


def test_choose_default_assets():
    img, gif1, gif2, music = choose_default_assets(ASSETS_DIR)
    assert img is not None and Path(img).exists()
    assert gif1 is not None and Path(gif1).exists()
    assert music is not None and Path(music).exists()
    # In bundled assets, we have 2 gifs
    assert gif2 is not None and Path(gif2).exists()


def test_sort_candidates(tmp_path):
    f_other = tmp_path / "zebra.png"
    f_pref = tmp_path / "unnamed.jpg"
    f_other.touch()
    f_pref.touch()

    sorted_list = sort_candidates([f_other, f_pref], ["unnamed.jpg"])
    assert sorted_list[0] == f_pref
    assert sorted_list[1] == f_other


def test_is_explicit_none():
    assert is_explicit_none("none") is True
    assert is_explicit_none("None") is True
    assert is_explicit_none("null") is True
    assert is_explicit_none("false") is True
    assert is_explicit_none("") is True
    assert is_explicit_none("   ") is True
    assert is_explicit_none("some_path.jpg") is False
    assert is_explicit_none(None) is False


def test_cli_parse_args_defaults():
    import re
    args = parse_args([])
    assert args.duration == 15.0
    assert args.gradient == "sunset"
    assert args.template == "modern_card"
    assert args.output == get_default_output_filename()
    assert re.match(r"^video_\d{4}-\d{2}-\d{2}\.mp4$", args.output)
    assert args.image is None
    assert args.no_image is False


def test_cli_duration_validation_exit():
    with pytest.raises(SystemExit) as exc_info:
        main(["--duration", "0.1"])
    assert exc_info.value.code == 2

    with pytest.raises(SystemExit) as exc_info2:
        main(["--duration", "9999.0"])
    assert exc_info2.value.code == 2


def test_cli_missing_file_validation_exit():
    with pytest.raises(SystemExit) as exc_info:
        main(["--image", "/path/to/non_existent_file.png"])
    assert exc_info.value.code == 2
