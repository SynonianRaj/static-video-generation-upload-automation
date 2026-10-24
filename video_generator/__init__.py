"""Video Generator package for 9:16 portrait videos."""
from .config import VideoConfig, GRADIENT_PRESETS
from .engine import VideoGenerator
from .gradients import get_colors_for_config, create_gradient_asset
from .overlays import create_master_overlay
from .audio import process_audio

__all__ = [
    "VideoConfig",
    "VideoGenerator",
    "GRADIENT_PRESETS",
    "get_colors_for_config",
    "create_gradient_asset",
    "create_master_overlay",
    "process_audio"
]
