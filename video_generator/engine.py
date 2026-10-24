"""Master video composition engine orchestrating multi-input FFmpeg rendering."""
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple

from .audio import process_audio
from .config import VideoConfig
from .gradients import create_gradient_asset
from .overlays import create_master_overlay

logger = logging.getLogger(__name__)


def check_ffmpeg_available() -> bool:
    """Returns True if ffmpeg executable is present on PATH."""
    return shutil.which("ffmpeg") is not None


class VideoGenerator:
    """Orchestrates the 9:16 portrait video generation process."""

    def __init__(self, config: Optional[VideoConfig] = None):
        self.config = config or VideoConfig()

    def generate(self, output_path: Optional[str] = None, timeout: Optional[float] = None) -> Path:
        """
        Executes the full pipeline:
        1. Validates system dependencies (ffmpeg)
        2. Background gradient (static or animated)
        3. Visual elements overlay & GIF slots
        4. Audio trimming/looping with fade-in & fade-out
        5. FFmpeg compositing into final 9:16 1080x1920 MP4
        """
        if not check_ffmpeg_available():
            raise RuntimeError(
                "ffmpeg executable not found in system PATH. "
                "Please install FFmpeg to render videos."
            )

        config = self.config
        final_output = Path(output_path or config.output_path).resolve()
        final_output.parent.mkdir(parents=True, exist_ok=True)

        temp_dir_obj = None
        if config.temp_dir:
            work_dir = Path(config.temp_dir)
            work_dir.mkdir(parents=True, exist_ok=True)
        else:
            temp_dir_obj = tempfile.TemporaryDirectory(prefix="video_gen_")
            work_dir = Path(temp_dir_obj.name)

        try:
            logger.info("Step 1/4: Generating background gradient (%s, %s)...", config.gradient_preset, config.gradient_mode)
            bg_gradient_path = work_dir / "bg_gradient.png"
            create_gradient_asset(config, bg_gradient_path)

            logger.info("Step 2/4: Generating master visual overlay...")
            overlay_path = work_dir / "overlay.png"
            _, gif1_slot, gif2_slot = create_master_overlay(config, overlay_path)

            logger.info("Step 3/4: Processing audio tracks...")
            processed_audio_path = work_dir / "processed_audio.aac"
            process_audio(config, processed_audio_path)

            logger.info("Step 4/4: Encoding final H.264 video with FFmpeg...")
            self._render_video(
                bg_gradient_path=bg_gradient_path,
                overlay_path=overlay_path,
                processed_audio_path=processed_audio_path,
                gif1_slot=gif1_slot,
                gif2_slot=gif2_slot,
                final_output=final_output,
                timeout=timeout
            )

            logger.info("Video generated successfully at: %s", final_output)
            return final_output

        finally:
            if temp_dir_obj:
                try:
                    temp_dir_obj.cleanup()
                except Exception as cleanup_err:
                    logger.warning("Could not cleanly remove temp directory: %s", cleanup_err)

    def _render_video(
        self,
        bg_gradient_path: Path,
        overlay_path: Path,
        processed_audio_path: Path,
        gif1_slot: Optional[Tuple[int, int, int, int]],
        gif2_slot: Optional[Tuple[int, int, int, int]],
        final_output: Path,
        timeout: Optional[float] = None
    ):
        """Constructs and executes the FFmpeg rendering command supporting dual animated GIFs."""
        config = self.config
        duration = max(0.5, float(config.duration))
        fps = max(1, int(config.fps))
        render_timeout = timeout or max(60.0, duration * 8.0)

        has_gif1 = bool(config.gif_path and Path(config.gif_path).exists() and gif1_slot)
        has_gif2 = bool(config.gif2_path and Path(config.gif2_path).exists() and gif2_slot)

        cmd = ["ffmpeg", "-y"]

        # Input 0: Background
        cmd.extend(["-loop", "1", "-t", str(duration), "-r", str(fps), "-i", str(bg_gradient_path)])

        # Input 1: Master Overlay
        cmd.extend(["-loop", "1", "-t", str(duration), "-r", str(fps), "-i", str(overlay_path)])

        current_input_idx = 2

        gif1_input_idx = None
        if has_gif1:
            cmd.extend(["-ignore_loop", "0", "-i", str(Path(config.gif_path).resolve())])
            gif1_input_idx = current_input_idx
            current_input_idx += 1

        gif2_input_idx = None
        if has_gif2:
            cmd.extend(["-ignore_loop", "0", "-i", str(Path(config.gif2_path).resolve())])
            gif2_input_idx = current_input_idx
            current_input_idx += 1

        # Input Audio
        audio_input_idx = current_input_idx
        cmd.extend(["-i", str(processed_audio_path)])

        # Construct Filter Complex Graph
        filter_chains = []

        # Background preparation
        if config.gradient_mode == "animated":
            filter_chains.append(
                f"[0:v] crop=w={config.width}:h={config.height}:"
                f"x='(in_w-out_w)/2 + 50*sin(2*PI*t/15)':"
                f"y='(in_h-out_h)/2 + 70*cos(2*PI*t/18)',"
                f"hue=H='2*PI*t/45' [bg]"
            )
        else:
            filter_chains.append(f"[0:v] scale={config.width}:{config.height} [bg]")

        # Overlay base cards/text
        filter_chains.append("[bg][1:v] overlay=0:0 [v_base]")
        current_v = "[v_base]"

        # Overlay GIF 1
        if has_gif1:
            gx1, gy1, gw1, gh1 = gif1_slot
            filter_chains.append(
                f"[{gif1_input_idx}:v] scale={gw1}:{gh1}:force_original_aspect_ratio=decrease,format=yuva420p [scaled_gif1]"
            )
            filter_chains.append(
                f"{current_v}[scaled_gif1] overlay={gx1}:y={gy1}:shortest=0 [v_after_gif1]"
            )
            current_v = "[v_after_gif1]"

        # Overlay GIF 2 (side-by-side in GIF row)
        if has_gif2:
            gx2, gy2, gw2, gh2 = gif2_slot
            filter_chains.append(
                f"[{gif2_input_idx}:v] scale={gw2}:{gh2}:force_original_aspect_ratio=decrease,format=yuva420p [scaled_gif2]"
            )
            filter_chains.append(
                f"{current_v}[scaled_gif2] overlay={gx2}:y={gy2}:shortest=0 [v_after_gif2]"
            )
            current_v = "[v_after_gif2]"

        filter_chains.append(f"{current_v} null [v_out]")

        filter_complex = "; ".join(filter_chains)

        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[v_out]",
            "-map", f"{audio_input_idx}:a",
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-ac", "2",
            "-movflags", "+faststart",
            str(final_output)
        ])

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=render_timeout
            )
            if result.returncode != 0:
                logger.error("FFmpeg failed with return code %d:\n%s", result.returncode, result.stderr)
                raise RuntimeError(f"FFmpeg rendering failed:\n{result.stderr.strip()[-400:]}")
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Video rendering timed out after {render_timeout}s")
