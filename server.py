"""Production-ready FastAPI web server for 9:16 portrait video generation."""
import asyncio
import logging
import os
import re
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from video_generator import VideoConfig, VideoGenerator, GRADIENT_PRESETS
from video_generator.audio import check_ffprobe_available
from video_generator.engine import check_ffmpeg_available
from video_generator.templates import TEMPLATES

# Logging configuration
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("video_generator_server")

SERVER_START_TIME = time.time()
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "web" / "static"
TEMPLATES_DIR = BASE_DIR / "web" / "templates"
OUTPUTS_DIR = BASE_DIR / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
DEMO_DIR = BASE_DIR / "assets" / "demo"

# Server Limits & Config
MAX_DURATION = float(os.getenv("MAX_DURATION", "60.0"))
MIN_DURATION = float(os.getenv("MIN_DURATION", "1.0"))
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "25"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_CONCURRENT_RENDERS = int(os.getenv("MAX_CONCURRENT_RENDERS", "2"))
RETENTION_MINUTES = int(os.getenv("OUTPUT_RETENTION_MINUTES", "120"))
CLEANUP_INTERVAL_MINUTES = int(os.getenv("CLEANUP_INTERVAL_MINUTES", "30"))

ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_GIF_EXTS = {".gif"}
ALLOWED_AUDIO_EXTS = {".mp3", ".mpeg", ".wav", ".m4a", ".aac", ".ogg", ".flac"}

SAFE_FILENAME_REGEX = re.compile(r"^video_[a-zA-Z0-9_\-]+\.mp4$")

render_semaphore = asyncio.Semaphore(MAX_CONCURRENT_RENDERS)


async def periodic_cleanup_task(interval_seconds: int = 1800, max_age_seconds: int = 7200):
    """Background task to remove old rendered videos and stale temp directories."""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            now = time.time()
            if OUTPUTS_DIR.exists():
                for item in OUTPUTS_DIR.iterdir():
                    if item.is_file() and item.name.startswith("video_") and item.suffix == ".mp4":
                        if now - item.stat().st_mtime > max_age_seconds:
                            try:
                                item.unlink(missing_ok=True)
                                logger.info("Cleaned up expired video: %s", item.name)
                            except Exception as e:
                                logger.warning("Could not delete expired video %s: %s", item.name, e)
                    elif item.is_dir() and item.name.startswith("temp_"):
                        if now - item.stat().st_mtime > 1800:
                            try:
                                shutil.rmtree(item, ignore_errors=True)
                                logger.info("Cleaned up stale temp dir: %s", item.name)
                            except Exception as e:
                                logger.warning("Could not delete stale temp dir %s: %s", item.name, e)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Error in periodic cleanup task: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    logger.info("Starting Video Generator Studio Server...")
    ffmpeg_ok = check_ffmpeg_available()
    ffprobe_ok = check_ffprobe_available()
    if not ffmpeg_ok:
        logger.warning("⚠️ FFmpeg is NOT found in PATH. Video rendering will fail until installed.")
    if not ffprobe_ok:
        logger.warning("⚠️ FFprobe is NOT found in PATH. Audio duration detection will fail until installed.")

    # Clean up any lingering temp directories on startup
    for item in OUTPUTS_DIR.glob("temp_*"):
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)

    cleanup_task_handle = asyncio.create_task(
        periodic_cleanup_task(
            interval_seconds=CLEANUP_INTERVAL_MINUTES * 60,
            max_age_seconds=RETENTION_MINUTES * 60
        )
    )

    yield

    logger.info("Shutting down Video Generator Studio Server...")
    cleanup_task_handle.cancel()
    try:
        await cleanup_task_handle
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="9:16 Portrait Video Generator Studio",
    description="High-performance API for creating aesthetic 9:16 portrait videos with typography, gradients, animated GIFs and audio.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS setup
cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if cors_origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_timing_middleware(request: Request, call_next):
    """Logs HTTP request timing and handles unhandled exceptions cleanly."""
    start_time = time.time()
    try:
        response = await call_next(request)
        duration_ms = (time.time() - start_time) * 1000
        logger.debug("%s %s -> %d (%.1fms)", request.method, request.url.path, response.status_code, duration_ms)
        return response
    except Exception as exc:
        duration_ms = (time.time() - start_time) * 1000
        logger.exception("Unhandled error on %s %s (%.1fms): %s", request.method, request.url.path, duration_ms, exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "detail": "Internal server error occurred."}
        )


# Mount static assets
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    html_file = TEMPLATES_DIR / "index.html"
    if not html_file.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return HTMLResponse(content=html_file.read_text(encoding="utf-8"))


@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestrators and load balancers."""
    ffmpeg_ok = check_ffmpeg_available()
    ffprobe_ok = check_ffprobe_available()

    try:
        disk_usage = shutil.disk_usage(OUTPUTS_DIR)
        disk_free_gb = round(disk_usage.free / (1024 ** 3), 2)
    except Exception:
        disk_free_gb = None

    is_healthy = ffmpeg_ok and ffprobe_ok
    status_code = status.HTTP_200_OK if is_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if is_healthy else "degraded",
            "version": "1.0.0",
            "uptime_seconds": round(time.time() - SERVER_START_TIME, 1),
            "ffmpeg_available": ffmpeg_ok,
            "ffprobe_available": ffprobe_ok,
            "disk_free_gb": disk_free_gb,
            "max_concurrent_renders": MAX_CONCURRENT_RENDERS,
        }
    )


@app.get("/api/info")
async def api_info():
    """Returns supported presets, templates, and validation constraints."""
    return {
        "gradient_presets": list(GRADIENT_PRESETS.keys()),
        "templates": list(TEMPLATES.keys()),
        "background_modes": ["static", "animated"],
        "max_duration": MAX_DURATION,
        "min_duration": MIN_DURATION,
        "max_file_size_mb": MAX_FILE_SIZE_MB,
    }


@app.get("/outputs/{filename}")
async def get_output_video(filename: str):
    """Safely retrieves a rendered video with path traversal prevention."""
    if not SAFE_FILENAME_REGEX.match(filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid video filename format."
        )

    file_path = (OUTPUTS_DIR / filename).resolve()
    # Ensure path stays strictly inside OUTPUTS_DIR
    try:
        if not file_path.is_relative_to(OUTPUTS_DIR.resolve()) or not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    except AttributeError:
        # Python < 3.9 fallback
        if str(file_path).startswith(str(OUTPUTS_DIR.resolve())) and file_path.exists() and file_path.is_file():
            pass
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    return FileResponse(
        file_path,
        media_type="video/mp4",
        filename=filename,
        headers={"Accept-Ranges": "bytes"}
    )


async def _save_upload_safely(
    upload: Optional[UploadFile],
    allowed_exts: set,
    dest_path: Path,
    max_bytes: int = MAX_FILE_SIZE_BYTES
) -> Optional[str]:
    """Saves uploaded file securely with chunked streaming and size limits."""
    if not upload or not upload.filename:
        return None

    raw_filename = Path(upload.filename).name
    ext = Path(raw_filename).suffix.lower()
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '{ext}'. Allowed: {', '.join(sorted(allowed_exts))}"
        )

    total_bytes = 0
    chunk_size = 64 * 1024
    with open(dest_path, "wb") as buffer:
        while chunk := await upload.read(chunk_size):
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                dest_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds maximum allowed size of {max_bytes // (1024 * 1024)} MB."
                )
            buffer.write(chunk)

    return str(dest_path)


@app.post("/api/generate")
async def api_generate_video(
    text: str = Form("Bhagwan ke naam pe is greeb ka help krdo 🙏🙏🙏\n1-2 rupaye hi dedo . plzzzz🙏😭"),
    date_text: Optional[str] = Form(None),
    gradient: str = Form("sunset"),
    bg_mode: str = Form("static"),
    template: str = Form("modern_card"),
    duration: float = Form(20.0),
    card_bg: Optional[str] = Form("false"),
    use_demo: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    gif: Optional[UploadFile] = File(None),
    gif2: Optional[UploadFile] = File(None),
    music: Optional[UploadFile] = File(None),
):
    """Renders 9:16 portrait video from user input or demo assets."""
    # 1. Input Validation
    if not text or not text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Text field cannot be empty.")
    if len(text) > 1000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Text exceeds maximum limit of 1000 characters.")

    if duration < MIN_DURATION or duration > MAX_DURATION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Duration must be between {MIN_DURATION} and {MAX_DURATION} seconds."
        )

    gradient_clean = gradient.lower().strip()
    if gradient_clean not in GRADIENT_PRESETS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid gradient preset '{gradient}'. Choices: {', '.join(GRADIENT_PRESETS.keys())}"
        )

    bg_mode_clean = bg_mode.lower().strip()
    if bg_mode_clean not in ("static", "animated"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Background mode must be either 'static' or 'animated'."
        )

    template_clean = template.lower().strip()
    if template_clean not in TEMPLATES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid template '{template}'. Choices: {', '.join(TEMPLATES.keys())}"
        )

    upload_id = uuid.uuid4().hex[:12]
    temp_upload_dir = OUTPUTS_DIR / f"temp_{upload_id}"
    temp_upload_dir.mkdir(parents=True, exist_ok=True)

    image_path: Optional[str] = None
    gif_path: Optional[str] = None
    gif2_path: Optional[str] = None
    music_path: Optional[str] = None

    try:
        # Load demo assets if requested
        if use_demo and use_demo.lower() in ("true", "1", "yes"):
            img_demo = DEMO_DIR / "unnamed.jpg"
            image_path = str(img_demo) if img_demo.exists() else str(DEMO_DIR / "sample_picture.png")

            gif1_demo = DEMO_DIR / "giphy.gif"
            gif_path = str(gif1_demo) if gif1_demo.exists() else str(DEMO_DIR / "sample_sticker.gif")

            gif2_demo = DEMO_DIR / "giphy1.gif"
            gif2_path = str(gif2_demo) if gif2_demo.exists() else None

            music_demo = DEMO_DIR / "bg.mpeg"
            music_path = str(music_demo) if music_demo.exists() else str(DEMO_DIR / "sample_music.mp3")

        # Save user uploaded files safely with randomized safe names
        if image and image.filename:
            image_path = await _save_upload_safely(
                image, ALLOWED_IMAGE_EXTS, temp_upload_dir / f"img_{upload_id}{Path(image.filename).suffix.lower()}"
            )

        if gif and gif.filename:
            gif_path = await _save_upload_safely(
                gif, ALLOWED_GIF_EXTS, temp_upload_dir / f"gif1_{upload_id}.gif"
            )

        if gif2 and gif2.filename:
            gif2_path = await _save_upload_safely(
                gif2, ALLOWED_GIF_EXTS, temp_upload_dir / f"gif2_{upload_id}.gif"
            )

        if music and music.filename:
            music_path = await _save_upload_safely(
                music, ALLOWED_AUDIO_EXTS, temp_upload_dir / f"music_{upload_id}{Path(music.filename).suffix.lower()}"
            )

        # Normalize texts
        clean_text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        clean_date = date_text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ").strip() if date_text else None

        video_filename = f"video_{upload_id}.mp4"
        final_video_path = OUTPUTS_DIR / video_filename

        config = VideoConfig(
            width=1080,
            height=1920,
            fps=30,
            duration=duration,
            gradient_preset=gradient_clean,
            gradient_mode=bg_mode_clean,
            template=template_clean,
            text=clean_text,
            date_text=clean_date if clean_date else None,
            text_card_bg=(card_bg and card_bg.lower() in ("true", "1", "yes")),
            image_path=image_path,
            gif_path=gif_path,
            gif2_path=gif2_path,
            music_path=music_path,
            output_path=str(final_video_path)
        )

        logger.info("Queuing video render task (upload_id: %s)...", upload_id)

        # Semaphore prevents OOM under concurrent traffic
        async with render_semaphore:
            logger.info("Executing render task %s on worker thread...", upload_id)
            generator = VideoGenerator(config)
            # Run CPU-bound subprocess execution off the async event loop
            await asyncio.to_thread(generator.generate)

        return {
            "status": "success",
            "video_url": f"/outputs/{video_filename}",
            "filename": video_filename
        }

    except HTTPException:
        raise
    except (ValueError, TimeoutError) as app_err:
        logger.warning("Render validation/timeout failure (%s): %s", upload_id, app_err)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(app_err))
    except Exception as exc:
        logger.exception("Unexpected error rendering video (%s): %s", upload_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Video rendering error: {str(exc)[:250]}"
        )
    finally:
        if temp_upload_dir.exists():
            shutil.rmtree(temp_upload_dir, ignore_errors=True)


def main():
    """CLI launcher for uvicorn server with environment configuration."""
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    reload = os.getenv("RELOAD", "false").lower() in ("true", "1", "yes")
    workers = int(os.getenv("WORKERS", "1"))

    logger.info("Starting Video Generator Studio on http://%s:%d (workers: %d, reload: %s)", host, port, workers, reload)
    uvicorn.run("server:app", host=host, port=port, reload=reload, workers=workers)


if __name__ == "__main__":
    main()
