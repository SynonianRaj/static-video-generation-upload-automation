"""Configuration classes and presets for 9:16 portrait video generation."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Tuple


GRADIENT_PRESETS = {
    "sunset": [
        (255, 65, 108),   # Vivid Pink-Red
        (255, 75, 43),    # Crimson Orange
        (255, 179, 71),   # Warm Peach Gold
    ],
    "cyberpunk": [
        (15, 12, 41),     # Midnight Indigo
        (48, 43, 99),     # Electric Violet
        (36, 198, 220),   # Neon Cyan
    ],
    "aurora": [
        (5, 25, 55),      # Deep Arctic Blue
        (0, 119, 137),    # Rich Teal
        (0, 209, 157),    # Luminous Emerald
    ],
    "royal_purple": [
        (20, 30, 48),     # Obsidian Navy
        (76, 0, 112),     # Royal Velvet Purple
        (157, 78, 221),   # Soft Amethyst
    ],
    "cotton_candy": [
        (244, 143, 177),  # Soft Blush
        (206, 147, 216),  # Pastel Lilac
        (144, 202, 249),  # Powder Sky Blue
    ],
    "midnight": [
        (15, 23, 42),     # Dark Slate Navy
        (30, 41, 59),     # Deep Gray Slate
        (51, 65, 85),     # Muted Steel
    ],
    "emerald": [
        (6, 78, 59),      # Deep Forest
        (16, 185, 129),   # Vivid Mint
        (110, 231, 183),  # Soft Sage Glow
    ],
    "dark_gold": [
        (26, 26, 26),     # Onyx Black
        (74, 55, 27),     # Bronze Brown
        (212, 175, 55),   # Imperial Gold
    ],
}


@dataclass
class VideoConfig:
    """Master configuration for generating a 9:16 portrait video."""
    width: int = 1080
    height: int = 1920
    fps: int = 30
    duration: float = 20.0

    # Background styling
    gradient_preset: str = "sunset"
    custom_colors: Optional[List[Tuple[int, int, int]]] = None
    gradient_mode: str = "static"  # "static" or "animated"
    gradient_type: str = "linear"  # "linear" or "radial"

    # Overlay assets
    image_path: Optional[str] = None
    gif_path: Optional[str] = None      # Primary GIF sticker
    gif2_path: Optional[str] = None     # Secondary GIF sticker (for dual GIF row)
    music_path: Optional[str] = None

    # Text content & styling
    text: str = "Create your story today ✨\nMake every second count 🚀"
    date_text: Optional[str] = None
    text_card_bg: bool = False  # False = fully transparent text container with text shadows

    # Layout template
    template: str = "modern_card"

    # Output options
    output_path: str = "output.mp4"
    temp_dir: Optional[str] = None

    # Audio options
    audio_fade_in: float = 0.5
    audio_fade_out: float = 2.0
