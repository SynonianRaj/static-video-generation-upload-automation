"""High-aesthetic gradient generator for 9:16 portrait video backgrounds."""
import math
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional
import numpy as np
from PIL import Image

from .config import GRADIENT_PRESETS, VideoConfig


def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
    """Converts hex color string to RGB tuple."""
    hex_str = hex_str.lstrip("#")
    if len(hex_str) == 3:
        hex_str = "".join([c * 2 for c in hex_str])
    return int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)


def get_colors_for_config(config: VideoConfig) -> List[Tuple[int, int, int]]:
    """Resolves RGB color stops from config."""
    if config.custom_colors and len(config.custom_colors) >= 2:
        return config.custom_colors
    preset_name = config.gradient_preset.lower()
    return GRADIENT_PRESETS.get(preset_name, GRADIENT_PRESETS["sunset"])


def generate_linear_gradient(
    width: int,
    height: int,
    colors: List[Tuple[int, int, int]],
    angle_deg: float = 135.0,
    add_dither: bool = True
) -> Image.Image:
    """
    Renders a multi-stop smooth linear gradient at a specified angle.
    Uses numpy for vectorized math and applies subtle dithering to prevent video banding.
    """
    # Create coordinate grid
    y_coords, x_coords = np.mgrid[0:height, 0:width]

    # Convert angle to radians
    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)

    # Project coordinates along gradient vector
    proj = x_coords * cos_a + y_coords * sin_a
    min_proj = proj.min()
    max_proj = proj.max()

    # Normalized 0.0 to 1.0 along the angle
    norm = (proj - min_proj) / (max_proj - min_proj + 1e-7)

    # Multi-stop color interpolation
    num_stops = len(colors)
    stops = np.linspace(0.0, 1.0, num_stops)

    r_channel = np.zeros((height, width), dtype=np.float32)
    g_channel = np.zeros((height, width), dtype=np.float32)
    b_channel = np.zeros((height, width), dtype=np.float32)

    for i in range(num_stops - 1):
        s0, s1 = stops[i], stops[i + 1]
        c0, c1 = colors[i], colors[i + 1]

        # Mask for pixels between current stops
        mask = (norm >= s0) & (norm <= s1) if i == num_stops - 2 else (norm >= s0) & (norm < s1)
        factor = np.clip((norm - s0) / (s1 - s0 + 1e-7), 0.0, 1.0)

        # Smooth cosine interpolation for smoother color flow
        smooth_t = (1.0 - np.cos(factor * np.pi)) / 2.0

        r_channel = np.where(mask, c0[0] + (c1[0] - c0[0]) * smooth_t, r_channel)
        g_channel = np.where(mask, c0[1] + (c1[1] - c0[1]) * smooth_t, g_channel)
        b_channel = np.where(mask, c0[2] + (c1[2] - c0[2]) * smooth_t, b_channel)

    # Subtle dithering / triangular noise to eliminate 8-bit banding in compressed H.264
    if add_dither:
        dither = (np.random.rand(height, width) - 0.5) * 1.5
        r_channel += dither
        g_channel += dither
        b_channel += dither

    r_channel = np.clip(r_channel, 0, 255).astype(np.uint8)
    g_channel = np.clip(g_channel, 0, 255).astype(np.uint8)
    b_channel = np.clip(b_channel, 0, 255).astype(np.uint8)

    rgb_array = np.dstack((r_channel, g_channel, b_channel))
    return Image.fromarray(rgb_array, mode="RGB")


def generate_radial_gradient(
    width: int,
    height: int,
    colors: List[Tuple[int, int, int]],
    center: Optional[Tuple[float, float]] = None,
    add_dither: bool = True
) -> Image.Image:
    """
    Renders a multi-stop radial spotlight gradient.
    """
    cx = center[0] * width if center else width * 0.5
    cy = center[1] * height if center else height * 0.4

    y_coords, x_coords = np.mgrid[0:height, 0:width]
    dist = np.sqrt((x_coords - cx) ** 2 + (y_coords - cy) ** 2)
    max_dist = math.sqrt(width ** 2 + height ** 2) * 0.65
    norm = np.clip(dist / max_dist, 0.0, 1.0)

    num_stops = len(colors)
    stops = np.linspace(0.0, 1.0, num_stops)

    r_channel = np.zeros((height, width), dtype=np.float32)
    g_channel = np.zeros((height, width), dtype=np.float32)
    b_channel = np.zeros((height, width), dtype=np.float32)

    for i in range(num_stops - 1):
        s0, s1 = stops[i], stops[i + 1]
        c0, c1 = colors[i], colors[i + 1]

        mask = (norm >= s0) & (norm <= s1) if i == num_stops - 2 else (norm >= s0) & (norm < s1)
        factor = np.clip((norm - s0) / (s1 - s0 + 1e-7), 0.0, 1.0)
        smooth_t = (1.0 - np.cos(factor * np.pi)) / 2.0

        r_channel = np.where(mask, c0[0] + (c1[0] - c0[0]) * smooth_t, r_channel)
        g_channel = np.where(mask, c0[1] + (c1[1] - c0[1]) * smooth_t, g_channel)
        b_channel = np.where(mask, c0[2] + (c1[2] - c0[2]) * smooth_t, b_channel)

    if add_dither:
        dither = (np.random.rand(height, width) - 0.5) * 1.5
        r_channel += dither
        g_channel += dither
        b_channel += dither

    r_channel = np.clip(r_channel, 0, 255).astype(np.uint8)
    g_channel = np.clip(g_channel, 0, 255).astype(np.uint8)
    b_channel = np.clip(b_channel, 0, 255).astype(np.uint8)

    rgb_array = np.dstack((r_channel, g_channel, b_channel))
    return Image.fromarray(rgb_array, mode="RGB")


def create_gradient_asset(
    config: VideoConfig,
    output_image_path: Path
) -> Path:
    """
    Creates the master background gradient image file.
    """
    colors = get_colors_for_config(config)

    # For animated mode, generate a slightly oversized canvas to enable smooth camera float / pan
    if config.gradient_mode == "animated":
        w = int(config.width * 1.25)
        h = int(config.height * 1.25)
    else:
        w = config.width
        h = config.height

    if config.gradient_type == "radial":
        img = generate_radial_gradient(w, h, colors)
    else:
        img = generate_linear_gradient(w, h, colors, angle_deg=135.0)

    output_image_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_image_path, format="PNG")
    return output_image_path
