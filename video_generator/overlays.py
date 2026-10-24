"""Compositor for text typography with full-color emojis, date badge, and framed pictures onto a transparent overlay."""
import datetime
from pathlib import Path
from typing import Optional, Tuple, List
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
from pilmoji import Pilmoji

from .config import VideoConfig
from .templates import get_template, LayoutSlots

BASE_DIR = Path(__file__).resolve().parent.parent
FONT_BOLD_PATH = BASE_DIR / "assets" / "fonts" / "LiberationSans-Bold.ttf"
FONT_REGULAR_PATH = BASE_DIR / "assets" / "fonts" / "LiberationSans-Regular.ttf"


def sanitize_text(text: Optional[str]) -> str:
    """Sanitizes text by normalizing CRLF to LF and stripping invalid control characters."""
    if not text:
        return ""
    clean = text.replace("\r\n", "\n").replace("\r", "\n")
    clean = "".join(ch for ch in clean if ch == "\n" or ch == "\t" or (ord(ch) >= 32 and ord(ch) != 127))
    return clean.strip()


def get_font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    """Loads TTF font with BASIC layout engine to ensure stability and emoji support."""
    try:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size, layout_engine=ImageFont.Layout.BASIC)
            except Exception:
                return ImageFont.truetype(str(path), size)
        return ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()


def render_rounded_rectangle(
    size: Tuple[int, int],
    radius: int,
    fill_color: Tuple[int, int, int, int],
    outline_color: Optional[Tuple[int, int, int, int]] = None,
    outline_width: int = 1
) -> Image.Image:
    """Renders an anti-aliased rounded rectangle."""
    scale = 2
    w, h = size[0] * scale, size[1] * scale
    r = radius * scale
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle(
        [(0, 0), (w - 1, h - 1)],
        radius=r,
        fill=fill_color,
        outline=outline_color,
        width=outline_width * scale
    )
    return img.resize(size, resample=Image.Resampling.LANCZOS)


def create_drop_shadow(
    image: Image.Image,
    offset: Tuple[int, int] = (0, 12),
    blur_radius: int = 24,
    shadow_color: Tuple[int, int, int, int] = (0, 0, 0, 100)
) -> Image.Image:
    """Creates a soft blurred drop shadow matching the image alpha channel."""
    alpha = image.split()[-1]
    w, h = image.size
    shadow = Image.new("RGBA", (w + blur_radius * 2, h + blur_radius * 2), (0, 0, 0, 0))
    shadow_img = Image.new("RGBA", (w, h), shadow_color)
    shadow.paste(shadow_img, (blur_radius + offset[0], blur_radius + offset[1]), mask=alpha)
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur_radius))
    return shadow


def format_current_date() -> str:
    """Formats current date for header badge (e.g. 'SATURDAY, OCTOBER 24, 2026')."""
    now = datetime.datetime.now()
    return now.strftime("%A, %B %d, %Y").upper()


def safe_textbbox(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> Tuple[int, int, int, int]:
    """Measures text bounding box safely with fallback to prevent layout engine crashes."""
    try:
        return draw.textbbox((0, 0), text, font=font)
    except Exception:
        approx_w = int(len(text) * font.size * 0.55)
        approx_h = int(font.size * 1.2)
        return (0, 0, approx_w, approx_h)


def render_date_badge(
    date_text: str,
    font: ImageFont.FreeTypeFont
) -> Image.Image:
    """Renders a sleek modern glassmorphic date pill badge with emoji support."""
    date_text = sanitize_text(date_text).replace("\n", " ")
    dummy_img = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(dummy_img)
    bbox = safe_textbbox(draw, date_text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    padding_x = 36
    padding_y = 14
    badge_w = text_w + padding_x * 2
    badge_h = text_h + padding_y * 2

    pill = render_rounded_rectangle(
        (badge_w, badge_h),
        radius=badge_h // 2,
        fill_color=(15, 23, 42, 160),
        outline_color=(255, 255, 255, 80),
        outline_width=2
    )

    tx = (badge_w - text_w) // 2
    ty = (badge_h - text_h) // 2 - bbox[1]

    with Pilmoji(pill) as pilmoji:
        pilmoji.text((tx, ty), date_text, font=font, fill=(255, 255, 255, 240))

    return pill


def wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int
) -> List[str]:
    """Wraps text into lines that do not exceed max_width."""
    text = sanitize_text(text)
    lines = []
    dummy = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(dummy)

    for paragraph in text.split("\n"):
        words = paragraph.split(" ")
        current_line = []
        for word in words:
            if not word:
                continue
            candidate = " ".join(current_line + [word])
            bbox = safe_textbbox(draw, candidate, font=font)
            if bbox[2] - bbox[0] <= max_width or not current_line:
                current_line.append(word)
            else:
                lines.append(" ".join(current_line))
                current_line = [word]
        if current_line:
            lines.append(" ".join(current_line))
    return lines or [""]


def render_framed_picture(
    image_path: str,
    target_box: Tuple[int, int, int, int],
    corner_radius: int = 24
) -> Tuple[Image.Image, int, int]:
    """
    Loads, scales, and frames user picture with rounded corners and drop shadow.
    Returns (composite_image, pos_x, pos_y).
    """
    max_x, max_y, max_w, max_h = target_box
    try:
        raw_img = Image.open(image_path)
        img = ImageOps.exif_transpose(raw_img) or raw_img
        img = img.convert("RGBA")
    except Exception as e:
        raise ValueError(f"Failed to load image '{Path(image_path).name}': {e}") from e

    orig_w, orig_h = img.size
    scale = min(max_w / orig_w, max_h / orig_h)
    new_w = int(orig_w * scale)
    new_h = int(orig_h * scale)

    resized = img.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)

    mask = Image.new("L", (new_w, new_h), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([(0, 0), (new_w - 1, new_h - 1)], radius=corner_radius, fill=255)
    resized.putalpha(mask)

    outline = render_rounded_rectangle(
        (new_w, new_h),
        radius=corner_radius,
        fill_color=(0, 0, 0, 0),
        outline_color=(255, 255, 255, 120),
        outline_width=2
    )
    framed = Image.alpha_composite(resized, outline)

    blur_r = 20
    shadow = create_drop_shadow(framed, offset=(0, 10), blur_radius=blur_r, shadow_color=(0, 0, 0, 110))

    comb_w = new_w + blur_r * 2
    comb_h = new_h + blur_r * 2
    combined = Image.new("RGBA", (comb_w, comb_h), (0, 0, 0, 0))
    combined.paste(shadow, (0, 0), mask=shadow)
    combined.paste(framed, (blur_r, blur_r), mask=framed)

    pos_x = max_x + (max_w - new_w) // 2 - blur_r
    pos_y = max_y + (max_h - new_h) // 2 - blur_r

    return combined, pos_x, pos_y


def render_text_block(
    text: str,
    target_box: Tuple[int, int, int, int],
    has_card_bg: bool = False,
    initial_font_size: int = 48,
    min_font_size: int = 28
) -> Tuple[Image.Image, int, int]:
    """
    Renders text with full-color emojis via pilmoji.
    If has_card_bg is False (default), text floats cleanly with high-contrast text shadow.
    If has_card_bg is True, draws a frosted dark card behind it.
    """
    text = sanitize_text(text)
    x, y, max_w, max_h = target_box
    padding_x = 30
    padding_y = 20
    inner_w = max_w - padding_x * 2

    font_size = initial_font_size
    best_lines = []
    best_font = None
    line_h = 0
    total_text_h = 0

    dummy = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(dummy)

    # Scale font size down until all text fits within bounds
    while font_size >= min_font_size:
        font = get_font(FONT_BOLD_PATH, font_size)
        lines = wrap_text(text, font, inner_w)
        line_spacing = int(font_size * 0.38)
        bbox = safe_textbbox(draw, "Aj", font=font)
        single_h = bbox[3] - bbox[1]
        line_h = single_h + line_spacing
        total_text_h = len(lines) * line_h - line_spacing
        if total_text_h <= (max_h - padding_y * 2) or font_size == min_font_size:
            best_lines = lines
            best_font = font
            break
        font_size -= 2

    card_w = max_w
    card_h = total_text_h + padding_y * 2
    card_h = min(card_h, max_h)

    text_canvas = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))

    if has_card_bg:
        card = render_rounded_rectangle(
            (card_w, card_h),
            radius=24,
            fill_color=(15, 23, 42, 180),
            outline_color=(255, 255, 255, 60),
            outline_width=2
        )
        text_canvas.paste(card, (0, 0), mask=card)

    start_y = (card_h - total_text_h) // 2

    # Render with Pilmoji for full-color emoji support
    with Pilmoji(text_canvas) as pilmoji:
        for i, line in enumerate(best_lines):
            line_bbox = safe_textbbox(draw, line, font=best_font)
            lw = line_bbox[2] - line_bbox[0]
            lx = (card_w - lw) // 2
            ly = start_y + i * line_h

            # Soft drop shadows behind text for legibility
            for ox, oy in [(-2, 0), (2, 0), (0, -2), (0, 2), (2, 3), (-2, 2)]:
                pilmoji.text(
                    (lx + ox, ly + oy),
                    line,
                    font=best_font,
                    fill=(0, 0, 0, 160)
                )

            # Main text + full color emojis
            pilmoji.text(
                (lx, ly),
                line,
                font=best_font,
                fill=(255, 255, 255, 255)
            )

    return text_canvas, x, y


def create_master_overlay(
    config: VideoConfig,
    output_overlay_path: Path
) -> Tuple[Path, Optional[Tuple[int, int, int, int]], Optional[Tuple[int, int, int, int]]]:
    """
    Renders all static visual elements onto a transparent 1080x1920 PNG.
    Returns:
        output_overlay_path: Path to rendered overlay PNG.
        gif1_slot: (x, y, target_w, target_h) for GIF 1.
        gif2_slot: (x, y, target_w, target_h) for GIF 2 (if present).
    """
    slots = get_template(config.template)
    canvas = Image.new("RGBA", (config.width, config.height), (0, 0, 0, 0))

    # 1. Date Badge (Shifted Up)
    date_str = config.date_text if config.date_text else format_current_date()
    date_font = get_font(FONT_BOLD_PATH, 28)
    badge = render_date_badge(date_str, date_font)
    badge_x = slots.date_pos[0] - badge.width // 2
    badge_y = slots.date_pos[1] - badge.height // 2
    canvas.paste(badge, (badge_x, badge_y), mask=badge)

    # 2. Framed Picture (Shifted Up)
    if config.image_path and Path(config.image_path).exists():
        pic_img, px, py = render_framed_picture(config.image_path, slots.image_box)
        canvas.paste(pic_img, (px, py), mask=pic_img)

    # 3. Main Text (Transparent Container with Emoji Support)
    if config.text:
        text_img, tx, ty = render_text_block(
            config.text,
            slots.text_box,
            has_card_bg=config.text_card_bg
        )
        canvas.paste(text_img, (tx, ty), mask=text_img)

    # Determine GIF slots
    has_gif1 = bool(config.gif_path and Path(config.gif_path).exists())
    has_gif2 = bool(config.gif2_path and Path(config.gif2_path).exists())

    if has_gif1 and has_gif2:
        # Dual GIF row
        gif1_slot = slots.gif_dual_box1
        gif2_slot = slots.gif_dual_box2
    elif has_gif1:
        # Single double-sized GIF
        gif1_slot = slots.gif_single_box
        gif2_slot = None
    elif has_gif2:
        # Only GIF 2 provided
        gif1_slot = slots.gif_single_box
        gif2_slot = None
    else:
        gif1_slot = None
        gif2_slot = None

    output_overlay_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_overlay_path, format="PNG")

    return output_overlay_path, gif1_slot, gif2_slot
