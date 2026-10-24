"""Unit and integration tests for 9:16 portrait video generator."""
import json
import subprocess
from pathlib import Path
from PIL import Image
import pytest

from video_generator import (
    VideoConfig,
    VideoGenerator,
    GRADIENT_PRESETS,
    get_colors_for_config,
    create_gradient_asset,
    create_master_overlay,
    process_audio,
)
from video_generator.gradients import generate_linear_gradient, generate_radial_gradient
from video_generator.templates import get_template, TEMPLATES
from video_generator.overlays import format_current_date, wrap_text, get_font, FONT_BOLD_PATH


def test_gradient_presets():
    assert "sunset" in GRADIENT_PRESETS
    assert "cyberpunk" in GRADIENT_PRESETS
    assert len(GRADIENT_PRESETS["sunset"]) >= 2


def test_linear_and_radial_gradients(tmp_path):
    colors = [(255, 0, 0), (0, 0, 255)]
    linear_img = generate_linear_gradient(108, 192, colors)
    assert linear_img.size == (108, 192)
    assert linear_img.mode == "RGB"

    radial_img = generate_radial_gradient(108, 192, colors)
    assert radial_img.size == (108, 192)
    assert radial_img.mode == "RGB"


def test_layout_templates():
    for name in ["modern_card", "showcase", "poster"]:
        slots = get_template(name)
        assert slots.date_pos[0] == 540  # Centered horizontally
        assert len(slots.image_box) == 4
        assert len(slots.text_box) == 4
        assert len(slots.gif_single_box) == 4
        assert len(slots.gif_dual_box1) == 4
        assert len(slots.gif_dual_box2) == 4


def test_typography_and_word_wrap():
    font = get_font(FONT_BOLD_PATH, 32)
    long_text = "This is a long sentence that should easily be split across multiple lines when wrapped."
    lines = wrap_text(long_text, font, max_width=300)
    assert len(lines) > 1


def test_master_overlay_generation(tmp_path):
    base_dir = Path(__file__).resolve().parent.parent
    demo_image = base_dir / "assets" / "demo" / "unnamed.jpg"

    config = VideoConfig(
        width=1080,
        height=1920,
        image_path=str(demo_image) if demo_image.exists() else None,
        text="Testing emoji typography ✨ 🚀 ❤️",
        date_text="SATURDAY, OCTOBER 24, 2026"
    )
    overlay_path = tmp_path / "test_overlay.png"
    out_path, gif1_slot, gif2_slot = create_master_overlay(config, overlay_path)

    assert out_path.exists()
    img = Image.open(out_path)
    assert img.size == (1080, 1920)
    assert img.mode == "RGBA"


def test_audio_processing(tmp_path):
    base_dir = Path(__file__).resolve().parent.parent
    demo_music = base_dir / "assets" / "demo" / "sample_music.mp3"

    config = VideoConfig(
        duration=20.0,
        music_path=str(demo_music) if demo_music.exists() else None
    )
    audio_out = tmp_path / "test_audio.aac"
    process_audio(config, audio_out)

    assert audio_out.exists()

    # Check ffprobe (raw ADTS stream has packet framing margin)
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(audio_out)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    duration = float(json.loads(res.stdout)["format"]["duration"])
    assert abs(duration - 20.0) < 0.5


def test_fast_video_generation(tmp_path):
    """End-to-end integration test creating a 5-second video."""
    base_dir = Path(__file__).resolve().parent.parent
    demo_image = base_dir / "assets" / "demo" / "sample_picture.png"
    demo_gif = base_dir / "assets" / "demo" / "sample_sticker.gif"
    demo_music = base_dir / "assets" / "demo" / "sample_music.mp3"

    video_out = tmp_path / "integration_test.mp4"
    config = VideoConfig(
        width=1080,
        height=1920,
        fps=30,
        duration=5.0,  # Fast 5s test
        gradient_preset="aurora",
        image_path=str(demo_image) if demo_image.exists() else None,
        gif_path=str(demo_gif) if demo_gif.exists() else None,
        music_path=str(demo_music) if demo_music.exists() else None,
        output_path=str(video_out)
    )

    generator = VideoGenerator(config)
    generator.generate()

    assert video_out.exists()
    assert video_out.stat().st_size > 50000  # At least 50KB

    # ffprobe check
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_name,width,height",
        "-show_entries", "format=duration",
        "-of", "json",
        str(video_out)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    probe = json.loads(res.stdout)

    v_stream = next(s for s in probe["streams"] if "width" in s)
    assert v_stream["width"] == 1080
    assert v_stream["height"] == 1920
    assert v_stream["codec_name"] == "h264"
    assert abs(float(probe["format"]["duration"]) - 5.0) < 0.2
