#!/usr/bin/env python3
"""Production-grade command-line interface for the 9:16 Portrait Video Generator."""
import argparse
from datetime import datetime
import logging
import random
import signal
import sys
from pathlib import Path
from typing import Optional, List, Tuple

from video_generator import VideoConfig, VideoGenerator, GRADIENT_PRESETS
from video_generator.audio import check_ffprobe_available
from video_generator.engine import check_ffmpeg_available
from video_generator.templates import TEMPLATES

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
DEMO_IMAGE = ASSETS_DIR / "demo" / "unnamed.jpg"
DEMO_GIF = ASSETS_DIR / "demo" / "giphy.gif"
DEMO_GIF2 = ASSETS_DIR / "demo" / "giphy1.gif"
DEMO_MUSIC = ASSETS_DIR / "demo" / "bg.mpeg"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
GIF_EXTENSIONS = {".gif"}
AUDIO_EXTENSIONS = {".mp3", ".mpeg", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".wma"}

PREFERRED_IMAGES = ["unnamed.jpg", "sample_picture.png"]
PREFERRED_GIFS = ["giphy.gif", "giphy1.gif", "sample_sticker.gif"]
PREFERRED_AUDIO = ["bg.mpeg", "sample_music.mp3"]


def setup_cli_logging(verbose: bool, quiet: bool):
    """Sets up console logging based on CLI flags."""
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format="[%(levelname)s] %(message)s"
    )


def discover_assets(assets_dir: Path) -> Tuple[List[Path], List[Path], List[Path]]:
    """
    Scans the given directory recursively for image, GIF, and audio files,
    ignoring font files and hidden files.
    """
    images: List[Path] = []
    gifs: List[Path] = []
    audio: List[Path] = []

    if not assets_dir.exists() or not assets_dir.is_dir():
        return images, gifs, audio

    for p in sorted(assets_dir.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        # Skip fonts folder
        if "fonts" in p.parts:
            continue

        ext = p.suffix.lower()
        if ext in GIF_EXTENSIONS:
            gifs.append(p)
        elif ext in IMAGE_EXTENSIONS:
            images.append(p)
        elif ext in AUDIO_EXTENSIONS:
            audio.append(p)

    return images, gifs, audio


def sort_candidates(candidates: List[Path], preferred_names: List[str]) -> List[Path]:
    """Sort candidate files prioritizing preferred demo assets, then by file path."""
    def priority_key(p: Path):
        name = p.name.lower()
        for idx, pref in enumerate(preferred_names):
            if name == pref.lower():
                return (0, idx)
        return (1, str(p).lower())

    return sorted(candidates, key=priority_key)


def choose_default_assets(
    assets_dir: Path, randomize: bool = False
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Chooses default image, gif1, gif2, and music from the assets folder.
    Returns:
        (image_path, gif1_path, gif2_path, music_path)
    """
    images, gifs, audio = discover_assets(assets_dir)

    if randomize:
        chosen_img = str(random.choice(images)) if images else None
        chosen_audio = str(random.choice(audio)) if audio else None
        if len(gifs) >= 2:
            sampled_gifs = random.sample(gifs, 2)
            chosen_gif1 = str(sampled_gifs[0])
            chosen_gif2 = str(sampled_gifs[1])
        elif len(gifs) == 1:
            chosen_gif1 = str(gifs[0])
            chosen_gif2 = None
        else:
            chosen_gif1 = None
            chosen_gif2 = None
        return chosen_img, chosen_gif1, chosen_gif2, chosen_audio

    # Deterministic priority-based sorting
    sorted_images = sort_candidates(images, PREFERRED_IMAGES)
    sorted_gifs = sort_candidates(gifs, PREFERRED_GIFS)
    sorted_audio = sort_candidates(audio, PREFERRED_AUDIO)

    chosen_img = str(sorted_images[0]) if sorted_images else None
    chosen_gif1 = str(sorted_gifs[0]) if sorted_gifs else None
    chosen_gif2 = str(sorted_gifs[1]) if len(sorted_gifs) > 1 else None
    chosen_audio = str(sorted_audio[0]) if sorted_audio else None

    return chosen_img, chosen_gif1, chosen_gif2, chosen_audio


def is_explicit_none(val: Optional[str]) -> bool:
    """Check if value explicitly indicates disabling the asset."""
    return val is not None and val.strip().lower() in ("none", "null", "false", "0", "")


def get_default_output_filename() -> str:
    """Returns default output filename containing current date: video_YYYY-MM-DD.mp4."""
    return f"video_{datetime.now().strftime('%Y-%m-%d')}.mp4"


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Configures and parses CLI command line arguments."""
    default_output = get_default_output_filename()
    parser = argparse.ArgumentParser(
        description="Production CLI for 9:16 Portrait Video Generator (1080x1920) with gradient backgrounds, pictures, emoji typography, dual live GIFs, and music."
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Run an instant end-to-end demonstration using the bundled demo assets."
    )
    parser.add_argument(
        "--text", type=str, default="Upar waale ke naam pe is greeb ka kuch help kr do 🙏🙏🙏🙏\n1-2 rupaye hi dedo, plzzzz🙏😭",
        help="Main text or quote to display (full emoji support enabled)."
    )
    parser.add_argument(
        "--date", type=str, default=None,
        help="Custom date text (e.g. 'October 24, 2026'). If omitted, current date is used."
    )
    parser.add_argument(
        "--image", type=str, default=None,
        help="Path to picture / image file (JPG, PNG, WebP). If omitted, chosen from assets/ folder. Pass 'none' or use --no-image to omit."
    )
    parser.add_argument(
        "--no-image", action="store_true",
        help="Disable picture overlay even if assets are available."
    )
    parser.add_argument(
        "--gif", type=str, default=None,
        help="Path to primary animated GIF sticker. If omitted, chosen from assets/ folder. Pass 'none' or use --no-gif to omit."
    )
    parser.add_argument(
        "--no-gif", action="store_true",
        help="Disable primary GIF sticker."
    )
    parser.add_argument(
        "--gif2", type=str, default=None,
        help="Path to secondary animated GIF sticker. If omitted, chosen from assets/ folder if available. Pass 'none' or use --no-gif2 to omit."
    )
    parser.add_argument(
        "--no-gif2", action="store_true",
        help="Disable secondary GIF sticker."
    )
    parser.add_argument(
        "--music", type=str, default=None,
        help="Path to background audio file (MP3, WAV, MPEG, M4A, etc.). If omitted, chosen from assets/ folder. Pass 'none' or use --no-music to omit."
    )
    parser.add_argument(
        "--no-music", action="store_true",
        help="Disable background music (synthesized ambient tone or silent)."
    )
    parser.add_argument(
        "--assets-dir", type=str, default=None,
        help="Path to custom assets directory to choose assets from (default: assets/)."
    )
    parser.add_argument(
        "--random-assets", action="store_true",
        help="Randomly pick assets from the assets directory if multiple candidates are available."
    )
    parser.add_argument(
        "--duration", type=float, default=15.0,
        help="Target video duration in seconds (default: 15.0)."
    )
    parser.add_argument(
        "--gradient", type=str, default="sunset",
        choices=list(GRADIENT_PRESETS.keys()),
        help=f"Gradient color palette: {', '.join(GRADIENT_PRESETS.keys())}."
    )
    parser.add_argument(
        "--bg-mode", type=str, default="static",
        choices=["static", "animated"],
        help="Background mode: 'static' or 'animated'."
    )
    parser.add_argument(
        "--template", type=str, default="modern_card",
        choices=list(TEMPLATES.keys()),
        help=f"Layout template style: {', '.join(TEMPLATES.keys())}."
    )
    parser.add_argument(
        "--card-bg", action="store_true", default=False,
        help="Enable frosted card background behind text (default: False, text is fully transparent)."
    )
    parser.add_argument(
        "--output", "-o", type=str, default=default_output,
        help=f"Path to save output video (default: '{default_output}')."
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable detailed debug output."
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Suppress informational console output."
    )

    return parser.parse_args(args)


def validate_file_exists(path_str: Optional[str], label: str):
    """Validates that a provided file path actually exists."""
    if path_str:
        p = Path(path_str)
        if not p.exists() or not p.is_file():
            print(f"❌ Error: {label} file not found at: {path_str}", file=sys.stderr)
            sys.exit(2)


def main(args_list: Optional[List[str]] = None):
    """Main execution function with proper exit codes and exception handling."""
    # Handle SIGINT gracefully
    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(130))

    args = parse_args(args_list)
    setup_cli_logging(args.verbose, args.quiet)

    # 1. Check system dependencies
    if not check_ffmpeg_available():
        print("❌ Error: FFmpeg is required but not installed or not in PATH.", file=sys.stderr)
        print("Please install ffmpeg (e.g. 'sudo apt install ffmpeg' or 'brew install ffmpeg').", file=sys.stderr)
        sys.exit(3)

    if not check_ffprobe_available():
        print("❌ Error: FFprobe is required but not installed or not in PATH.", file=sys.stderr)
        sys.exit(3)

    # 2. Validate duration
    if args.duration < 0.5 or args.duration > 300.0:
        print("❌ Error: Duration must be between 0.5 and 300.0 seconds.", file=sys.stderr)
        sys.exit(2)

    # 3. Validate user-specified file paths
    validate_file_exists(args.image if not is_explicit_none(args.image) else None, "Image")
    validate_file_exists(args.gif if not is_explicit_none(args.gif) else None, "GIF 1")
    validate_file_exists(args.gif2 if not is_explicit_none(args.gif2) else None, "GIF 2")
    validate_file_exists(args.music if not is_explicit_none(args.music) else None, "Music")

    assets_dir = Path(args.assets_dir).resolve() if args.assets_dir else ASSETS_DIR

    # Choose default assets from assets folder
    def_img, def_gif1, def_gif2, def_music = choose_default_assets(
        assets_dir, randomize=args.random_assets
    )

    if args.demo:
        if not args.quiet:
            print("🎬 Running 1-click Demo with user assets...")
        image_path = str(DEMO_IMAGE) if DEMO_IMAGE.exists() else def_img
        gif_path = str(DEMO_GIF) if DEMO_GIF.exists() else def_gif1
        gif2_path = str(DEMO_GIF2) if DEMO_GIF2.exists() else def_gif2
        music_path = str(DEMO_MUSIC) if DEMO_MUSIC.exists() else def_music
        output_path = "output_demo.mp4" if args.output == get_default_output_filename() else args.output
        text = args.text or "Upar waale ke naam pe is greeb ka kuch help kr do 🙏🙏🙏🙏\n1-2 rupaye hi dedo, plzzzz🙏😭"
    else:
        # Determine image
        if args.no_image or is_explicit_none(args.image):
            image_path = None
        elif args.image:
            image_path = args.image
        else:
            image_path = def_img

        # Determine GIF 1
        if args.no_gif or is_explicit_none(args.gif):
            gif_path = None
        elif args.gif:
            gif_path = args.gif
        else:
            gif_path = def_gif1

        # Determine GIF 2
        if args.no_gif2 or is_explicit_none(args.gif2):
            gif2_path = None
        elif args.gif2:
            gif2_path = args.gif2
        else:
            gif2_path = def_gif2

        # Determine Music
        if args.no_music or is_explicit_none(args.music):
            music_path = None
        elif args.music:
            music_path = args.music
        else:
            music_path = def_music

        output_path = args.output
        text = args.text

    # Inform user if assets were auto-selected from assets directory
    if not args.demo and not args.quiet:
        auto_selected = []
        if not args.image and not args.no_image and image_path:
            auto_selected.append(f"Image: {Path(image_path).name}")
        if not args.gif and not args.no_gif and gif_path:
            auto_selected.append(f"GIF 1: {Path(gif_path).name}")
        if not args.gif2 and not args.no_gif2 and gif2_path:
            auto_selected.append(f"GIF 2: {Path(gif2_path).name}")
        if not args.music and not args.no_music and music_path:
            auto_selected.append(f"Music: {Path(music_path).name}")

        if auto_selected:
            print(f"📦 Assets auto-selected from '{assets_dir.name}/': {', '.join(auto_selected)}")

    config = VideoConfig(
        width=1080,
        height=1920,
        fps=30,
        duration=args.duration,
        gradient_preset=args.gradient,
        gradient_mode=args.bg_mode,
        template=args.template,
        text=text,
        date_text=args.date,
        text_card_bg=args.card_bg,
        image_path=image_path,
        gif_path=gif_path,
        gif2_path=gif2_path,
        music_path=music_path,
        output_path=output_path
    )

    if not args.quiet:
        print(f"✨ Generating 9:16 Portrait Video ({config.width}x{config.height} @ {config.fps}fps)...")
        print(f"⏱️  Duration: {config.duration}s | Gradient: {config.gradient_preset} ({config.gradient_mode})")
        print(f"🖼️  Image: {image_path}")
        print(f"💫 GIF 1: {gif_path}")
        print(f"💫 GIF 2: {gif2_path}")
        print(f"🎵 Music: {music_path}")
        print(f"📝 Text (Transparent: {not config.text_card_bg}): {text.replace(chr(10), ' ')}")

    generator = VideoGenerator(config)
    try:
        out_file = generator.generate(output_path)
        if not args.quiet:
            print(f"\n✅ Video generated successfully: {out_file}")
            print(f"📁 File size: {out_file.stat().st_size / (1024 * 1024):.2f} MB")
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted by user. Cleaning up...", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error generating video: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
