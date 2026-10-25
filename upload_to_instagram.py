#!/usr/bin/env python3
"""
Automated Instagram Reel Publisher with Date-Based Tracking,
Previous-Day Failure Recovery, and Post-Upload Cleanup.

Features:
- Discovers date-stamped video files (e.g. video_YYYY-MM-DD.mp4)
- Identifies and prioritizes previous-date videos that failed in earlier runs
- Uploads to temporary direct HTTPS host (Catbox)
- Creates and polls Instagram Reel container via Graph API
- Publishes Reel to Instagram Creator/Business account
- Deletes the local video file immediately upon confirmed publication
- Keeps un-uploaded files intact upon failure for subsequent retry
- Supports --dry-run for non-destructive pipeline testing
"""

import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
DATE_REGEX = re.compile(r"video_(\d{4}-\d{2}-\d{2})")

DEFAULT_CAPTION = (
    "Upar waale ke naam pe is greeb ka kuch help kr do 🙏🙏🙏🙏\n"
    "1-2 rupaye hi dedo, plzzzz🙏😭\n\n"
    "#reels #help #explore #trending #instagram"
)


def load_env_file(env_path: Optional[Path] = None):
    """Loads environment variables from a local .env file if not already present."""
    path = env_path or (BASE_DIR / ".env")
    if not path.is_file():
        return

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("\"'")
                # Allow encoded newlines in caption
                v = v.replace("\\n", "\n")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception as e:
        logging.warning("Failed reading .env file: %s", e)


def get_credentials(
    cli_token: Optional[str] = None,
    cli_account_id: Optional[str] = None
) -> Tuple[str, str]:
    """Retrieves access token and account ID from CLI or environment."""
    load_env_file()
    token = cli_token or os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
    account_id = cli_account_id or os.environ.get("INSTAGRAM_ACCOUNT_ID", "").strip()

    if not token:
        raise ValueError("Missing Instagram Access Token. Set INSTAGRAM_ACCESS_TOKEN or pass --token.")
    if not account_id:
        raise ValueError("Missing Instagram Account ID. Set INSTAGRAM_ACCOUNT_ID or pass --account-id.")

    return token, account_id


def upload_to_uguu(video_path: Path, max_retries: int = 3) -> str:
    """Uploads video to uguu.se (ephemeral direct streamable HTTPS host, CI/CD friendly)."""
    url = "https://uguu.se/upload"
    boundary = "----WebKitFormBoundary" + os.urandom(16).hex()

    with open(video_path, "rb") as f:
        file_bytes = f.read()

    filename = video_path.name
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="files[]"; filename="{filename}"\r\n'
        f"Content-Type: video/mp4\r\n\r\n"
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "curl/7.88.1",
    }

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            logging.info("Uploading %s to Uguu (attempt %d/%d)...", filename, attempt, max_retries)
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("success") and data.get("files"):
                    uploaded_url = data["files"][0]["url"]
                    logging.info("Upload successful via Uguu: %s", uploaded_url)
                    return uploaded_url
                raise RuntimeError(f"Unexpected Uguu response: {data}")
        except Exception as e:
            last_error = e
            logging.warning("Uguu upload attempt %d failed: %s", attempt, e)
            if attempt < max_retries:
                time.sleep(2 * attempt)

    raise RuntimeError(f"Uguu upload failed: {last_error}")


def upload_to_catbox(video_path: Path, max_retries: int = 2) -> str:
    """Uploads video to catbox.moe as fallback."""
    url = "https://catbox.moe/user/api.php"
    boundary = "----WebKitFormBoundary" + os.urandom(16).hex()

    with open(video_path, "rb") as f:
        file_bytes = f.read()

    filename = video_path.name
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="reqtype"\r\n\r\nfileupload\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="fileToUpload"; filename="{filename}"\r\n'
        f"Content-Type: video/mp4\r\n\r\n"
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            logging.info("Uploading %s to Catbox fallback (attempt %d/%d)...", filename, attempt, max_retries)
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                resp_text = resp.read().decode("utf-8").strip()
                if resp_text.startswith("http://") or resp_text.startswith("https://"):
                    logging.info("Upload successful via Catbox: %s", resp_text)
                    return resp_text
                raise RuntimeError(f"Unexpected Catbox response: {resp_text}")
        except Exception as e:
            last_error = e
            logging.warning("Catbox upload attempt %d failed: %s", attempt, e)
            if attempt < max_retries:
                time.sleep(2 * attempt)

    raise RuntimeError(f"Catbox upload failed: {last_error}")


def upload_to_public_host(video_path: Path) -> str:
    """
    Uploads a video to a temporary direct streamable HTTPS host.
    Tries Uguu first (CI/CD datacenter friendly), falls back to Catbox.
    """
    if not video_path.is_file():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    try:
        return upload_to_uguu(video_path)
    except Exception as e:
        logging.warning("Primary host (Uguu) failed: %s. Trying fallback host...", e)
        return upload_to_catbox(video_path)


def create_reel_container(
    account_id: str,
    access_token: str,
    video_url: str,
    caption: str,
    max_retries: int = 3
) -> str:
    """
    Creates an Instagram Reel container via the Graph API.
    Returns the container ID.
    """
    endpoint = f"https://graph.instagram.com/v21.0/{account_id}/media"
    payload = urllib.parse.urlencode({
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": access_token
    }).encode("utf-8")

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            logging.info("Creating Instagram Reel container (attempt %d/%d)...", attempt, max_retries)
            req = urllib.request.Request(endpoint, data=payload)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                container_id = data.get("id")
                if not container_id:
                    raise RuntimeError(f"No container ID returned: {data}")
                logging.info("Reel container created: %s", container_id)
                return container_id
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            last_error = f"HTTP {e.code}: {err_body}"
            logging.warning("Container creation failed: %s", last_error)
            if attempt < max_retries:
                time.sleep(3 * attempt)
        except Exception as e:
            last_error = str(e)
            logging.warning("Container creation error: %s", last_error)
            if attempt < max_retries:
                time.sleep(3 * attempt)

    raise RuntimeError(f"Failed to create Reel container: {last_error}")


def wait_for_container_ready(
    container_id: str,
    access_token: str,
    timeout_seconds: int = 300,
    poll_interval: int = 5
) -> bool:
    """
    Polls the container status until 'FINISHED'.
    Raises an exception if 'ERROR', 'EXPIRED', or timeout occurs.
    """
    status_url = f"https://graph.instagram.com/v21.0/{container_id}?fields=status_code,status&access_token={access_token}"
    start_time = time.time()

    logging.info("Waiting for Instagram to process video container %s...", container_id)
    while time.time() - start_time < timeout_seconds:
        try:
            req = urllib.request.Request(status_url)
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                status_code = data.get("status_code", "").upper()
                logging.info("Container %s status: %s", container_id, status_code or "UNKNOWN")

                if status_code == "FINISHED":
                    return True
                if status_code in ("ERROR", "EXPIRED"):
                    raise RuntimeError(f"Container processing failed with status: {status_code} ({data})")

        except urllib.error.HTTPError as e:
            logging.warning("Status check transient error: %s", e)
        except Exception as e:
            if "Container processing failed" in str(e):
                raise
            logging.warning("Status check network error: %s", e)

        time.sleep(poll_interval)

    raise TimeoutError(f"Container {container_id} processing timed out after {timeout_seconds} seconds")


def publish_reel_container(
    account_id: str,
    access_token: str,
    container_id: str,
    max_retries: int = 3
) -> str:
    """
    Publishes a FINISHED Reel container.
    Returns the published Instagram Media ID.
    """
    endpoint = f"https://graph.instagram.com/v21.0/{account_id}/media_publish"
    payload = urllib.parse.urlencode({
        "creation_id": container_id,
        "access_token": access_token
    }).encode("utf-8")

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            logging.info("Publishing Reel container %s...", container_id)
            req = urllib.request.Request(endpoint, data=payload)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                media_id = data.get("id")
                if not media_id:
                    raise RuntimeError(f"No media ID in publish response: {data}")
                logging.info("🎉 Reel published successfully! Media ID: %s", media_id)
                return media_id
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            last_error = f"HTTP {e.code}: {err_body}"
            logging.warning("Publish attempt %d failed: %s", attempt, last_error)
            if attempt < max_retries:
                time.sleep(3 * attempt)
        except Exception as e:
            last_error = str(e)
            logging.warning("Publish error: %s", last_error)
            if attempt < max_retries:
                time.sleep(3 * attempt)

    raise RuntimeError(f"Failed to publish Reel: {last_error}")


def discover_pending_videos(search_dir: Optional[Path] = None) -> List[Tuple[Path, datetime]]:
    """
    Discovers all date-stamped video files (video_*.mp4) in search_dir.
    Returns a list of (Path, datetime) tuples sorted chronologically (oldest first).
    """
    directory = search_dir or Path.cwd()
    videos: List[Tuple[Path, datetime]] = []

    for file_path in directory.glob("video_*.mp4"):
        if not file_path.is_file():
            continue

        match = DATE_REGEX.search(file_path.name)
        if match:
            try:
                file_date = datetime.strptime(match.group(1), "%Y-%m-%d")
            except ValueError:
                file_date = datetime.fromtimestamp(file_path.stat().st_mtime)
        else:
            file_date = datetime.fromtimestamp(file_path.stat().st_mtime)

        videos.append((file_path, file_date))

    # Sort chronologically (oldest first)
    videos.sort(key=lambda item: item[1])
    return videos


def process_video_upload(
    video_path: Path,
    video_date: datetime,
    account_id: str,
    access_token: str,
    caption: str,
    dry_run: bool = False
) -> Optional[str]:
    """
    Executes the end-to-end upload, publishing, and deletion pipeline for a single video.
    Returns the published media ID, or None if in dry-run mode.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    is_previous_date = video_date.strftime("%Y-%m-%d") < today_str

    if is_previous_date:
        logging.info("⚠️ [PREVIOUS DATE RETRY] Video %s is from a prior failed run (%s). Prioritizing upload!",
                     video_path.name, video_date.strftime("%Y-%m-%d"))
    else:
        logging.info("📅 [TODAY'S SCHEDULE] Video %s is scheduled for today (%s).",
                     video_path.name, video_date.strftime("%Y-%m-%d"))

    # 1. Upload to public temporary host
    public_url = upload_to_public_host(video_path)

    # 2. Create Instagram container
    container_id = create_reel_container(account_id, access_token, public_url, caption)

    # 3. Poll container until ready
    wait_for_container_ready(container_id, access_token)

    if dry_run:
        logging.info("[DRY-RUN] Container %s verified FINISHED. Skipping live publish and file deletion.", container_id)
        return None

    # 4. Publish live Reel
    media_id = publish_reel_container(account_id, access_token, container_id)

    # 5. Delete file upon confirmed success
    try:
        video_path.unlink()
        logging.info("🗑️ [CLEANUP] Deleted %s after successful publication.", video_path.name)
    except Exception as e:
        logging.warning("Failed to delete %s: %s", video_path.name, e)

    return media_id


def check_token_status(access_token: str) -> None:
    """Checks the validity and expiration of the Instagram access token."""
    url = f"https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token={access_token}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            expires_in = data.get("expires_in", 0)
            days = round(expires_in / 86400, 1)
            print(f"✅ Token is valid! Expires in {expires_in} seconds (~{days} days).")
    except Exception as e:
        print(f"❌ Error checking token status: {e}", file=sys.stderr)


def main(args_list: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Automated Instagram Reel Publisher with Date-Based Tracking, Failure Recovery, and Cleanup."
    )
    parser.add_argument(
        "--video", type=str, default=None,
        help="Path to specific video file to upload. If omitted, discovers all video_*.mp4 chronologically."
    )
    parser.add_argument(
        "--caption", type=str, default=None,
        help="Custom caption for Reel. If omitted, uses INSTAGRAM_CAPTION env var or default quote."
    )
    parser.add_argument(
        "--token", type=str, default=None,
        help="Instagram Access Token (defaults to INSTAGRAM_ACCESS_TOKEN env var)."
    )
    parser.add_argument(
        "--account-id", type=str, default=None,
        help="Instagram Account ID (defaults to INSTAGRAM_ACCOUNT_ID env var)."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Verify video upload and container creation without publishing live or deleting the file."
    )
    parser.add_argument(
        "--check-token", action="store_true",
        help="Inspect access token validity and expiration."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable verbose debug logging."
    )

    args = parser.parse_args(args_list)

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(message)s")

    logging.info("🚀 Starting Instagram Reel Automation v1.2 (Host: Uguu with Catbox fallback)")

    try:
        token, account_id = get_credentials(args.token, args.account_id)
    except ValueError as e:
        logging.error("%s", e)
        return 1

    if args.check_token:
        check_token_status(token)
        return 0

    caption = args.caption or os.environ.get("INSTAGRAM_CAPTION") or DEFAULT_CAPTION

    # Specific file provided
    if args.video:
        target_path = Path(args.video).resolve()
        if not target_path.is_file():
            logging.error("Target video not found: %s", target_path)
            return 2
        match = DATE_REGEX.search(target_path.name)
        video_date = datetime.strptime(match.group(1), "%Y-%m-%d") if match else datetime.fromtimestamp(target_path.stat().st_mtime)
        pending = [(target_path, video_date)]
    else:
        pending = discover_pending_videos()

    if not pending:
        logging.info("No pending video files found to upload (matching 'video_*.mp4').")
        return 0

    logging.info("Found %d pending video file(s) to process.", len(pending))
    for p, d in pending:
        logging.info(" - %s (Date: %s)", p.name, d.strftime("%Y-%m-%d"))

    # Process all pending videos sequentially
    for video_path, video_date in pending:
        try:
            process_video_upload(
                video_path=video_path,
                video_date=video_date,
                account_id=account_id,
                access_token=token,
                caption=caption,
                dry_run=args.dry_run
            )
        except Exception as e:
            logging.error("❌ Failed to process %s: %s", video_path.name, e)
            logging.error("File %s remains on disk for subsequent retry.", video_path.name)
            return 1

    logging.info("🎉 All pending videos processed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
