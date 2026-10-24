"""Layout templates and slot geometries for 9:16 portrait video elements."""
from dataclasses import dataclass
from typing import Tuple, Optional


@dataclass
class LayoutSlots:
    """Bounding boxes and positions (x, y, w, h) for canvas elements."""
    date_pos: Tuple[int, int]                  # (center_x, center_y)
    image_box: Tuple[int, int, int, int]       # (x, y, max_w, max_h)
    text_box: Tuple[int, int, int, int]        # (x, y, max_w, max_h)
    gif_single_box: Tuple[int, int, int, int]  # (x, y, target_w, target_h) when 1 GIF is present (600x600)
    gif_dual_box1: Tuple[int, int, int, int]   # Slot 1 when 2 GIFs are present (460x460)
    gif_dual_box2: Tuple[int, int, int, int]   # Slot 2 when 2 GIFs are present (460x460)


TEMPLATES = {
    # Modern Card: Shifted up, transparent text, double-sized GIF row
    "modern_card": LayoutSlots(
        date_pos=(540, 110),
        image_box=(120, 170, 840, 700),
        text_box=(100, 890, 880, 270),
        gif_single_box=(240, 1200, 600, 600),
        gif_dual_box1=(60, 1240, 460, 460),
        gif_dual_box2=(560, 1240, 460, 460),
    ),
    # Showcase: Shifted up, prominent image, dual GIF row
    "showcase": LayoutSlots(
        date_pos=(540, 110),
        text_box=(100, 160, 880, 200),
        image_box=(120, 380, 840, 780),
        gif_single_box=(240, 1200, 600, 600),
        gif_dual_box1=(60, 1220, 460, 460),
        gif_dual_box2=(560, 1220, 460, 460),
    ),
    # Poster: Editorial typography, center image, dual GIF row
    "poster": LayoutSlots(
        date_pos=(540, 110),
        text_box=(100, 170, 880, 250),
        image_box=(120, 440, 840, 720),
        gif_single_box=(240, 1200, 600, 600),
        gif_dual_box1=(60, 1220, 460, 460),
        gif_dual_box2=(560, 1220, 460, 460),
    ),
}


def get_template(name: str) -> LayoutSlots:
    """Returns layout slots for given template name."""
    return TEMPLATES.get(name.lower(), TEMPLATES["modern_card"])
