"""Audio processing engine: duration detection, trimming, looping, and fade in/out."""
import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from .config import VideoConfig

logger = logging.getLogger(__name__)


def check_ffprobe_available() -> bool:
    """Returns True if ffprobe executable is present on PATH."""
    return shutil.which("ffprobe") is not None


def get_audio_duration(audio_path: str, timeout: float = 15.0) -> float:
    """
    Returns the duration of an audio file in seconds via ffprobe.
    Raises ValueError if file is corrupted or unreadable.
    """
    if not check_ffprobe_available():
        raise RuntimeError("ffprobe is not installed or not in PATH")

    path_obj = Path(audio_path)
    if not path_obj.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(path_obj.resolve())
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout
        )
        data = json.loads(result.stdout)
        duration_val = data.get("format", {}).get("duration")
        if duration_val is None:
            raise ValueError(f"Could not read duration from audio file: {audio_path}")
        return float(duration_val)
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"ffprobe timed out while analyzing audio file: {audio_path}")
    except (subprocess.CalledProcessError, json.JSONDecodeError, ValueError) as err:
        logger.error("Failed to probe audio file %s: %s", audio_path, err)
        raise ValueError(f"Invalid or corrupted audio file '{path_obj.name}': {err}") from err


def process_audio(
    config: VideoConfig,
    output_audio_path: Path,
    timeout: Optional[float] = None
) -> Optional[Path]:
    """
    Processes input audio to exactly `config.duration` seconds:
    - If audio > duration: trims to duration with smooth 2s fade-out.
    - If audio < duration: loops to fill duration with smooth fade-out.
    - If no audio provided: synthesizes a subtle warm ambient chord progression.
    Returns path to the processed audio file.
    """
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is not installed or not in PATH")

    duration = max(0.5, float(config.duration))
    fade_in = max(0.0, float(config.audio_fade_in))
    fade_out = max(0.0, float(config.audio_fade_out))
    fade_out_start = max(0.0, duration - fade_out)
    proc_timeout = timeout or max(45.0, duration * 3.0)

    output_audio_path.parent.mkdir(parents=True, exist_ok=True)

    if config.music_path and Path(config.music_path).exists():
        input_audio = Path(config.music_path).resolve()
        actual_len = get_audio_duration(str(input_audio))

        # Audio filter graph: Loop if needed, trim to duration, apply fade in/out
        if actual_len < duration:
            loops = int(duration / max(0.1, actual_len)) + 1
            audio_filter = (
                f"aloop=loop={loops}:size=2e+09,"
                f"atrim=0:{duration},"
                f"asetpts=PTS-STARTPTS,"
                f"afade=t=in:ss=0:d={fade_in},"
                f"afade=t=out:st={fade_out_start}:d={fade_out},"
                f"aformat=sample_rates=44100:channel_layouts=stereo"
            )
        else:
            audio_filter = (
                f"atrim=0:{duration},"
                f"asetpts=PTS-STARTPTS,"
                f"afade=t=in:ss=0:d={fade_in},"
                f"afade=t=out:st={fade_out_start}:d={fade_out},"
                f"aformat=sample_rates=44100:channel_layouts=stereo"
            )

        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_audio),
            "-af", audio_filter,
            "-t", str(duration),
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-ac", "2",
            str(output_audio_path)
        ]
        try:
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=proc_timeout
            )
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Audio processing timed out after {proc_timeout}s")
        except subprocess.CalledProcessError as e:
            logger.error("FFmpeg audio filter failed: %s", e.stderr)
            raise RuntimeError(f"Audio processing failed: {e.stderr.strip()[:300]}") from e

        return output_audio_path

    # Synthesize a subtle, warm ambient chord progression if no music provided
    synth_filter = (
        f"anoisesrc=d={duration}:c=pink:r=44100:a=0.015 [noise]; "
        f"sine=f=220:d={duration} [s1]; "
        f"sine=f=277.18:d={duration} [s2]; "
        f"sine=f=329.63:d={duration} [s3]; "
        f"[noise][s1][s2][s3] amix=inputs=4:dropout_transition=0, "
        f"afade=t=in:ss=0:d={fade_in},"
        f"afade=t=out:st={fade_out_start}:d={fade_out},"
        f"volume=1.2,"
        f"aformat=sample_rates=44100:channel_layouts=stereo"
    )
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", synth_filter,
        "-t", str(duration),
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",
        "-ac", "2",
        str(output_audio_path)
    ]
    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=proc_timeout
        )
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"Ambient audio synthesis timed out after {proc_timeout}s")
    except subprocess.CalledProcessError as e:
        logger.error("FFmpeg ambient synthesis failed: %s", e.stderr)
        raise RuntimeError(f"Ambient audio synthesis failed: {e.stderr.strip()[:300]}") from e

    return output_audio_path
