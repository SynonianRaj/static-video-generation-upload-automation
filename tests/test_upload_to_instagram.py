"""Unit tests for upload_to_instagram.py."""
import io
import json
import urllib.error
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from upload_to_instagram import (
    create_reel_container,
    discover_pending_videos,
    get_credentials,
    process_video_upload,
    publish_reel_container,
    upload_to_public_host,
    wait_for_container_ready,
)


def test_get_credentials(monkeypatch):
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "mock_token")
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_ID", "123456789")

    token, account_id = get_credentials()
    assert token == "mock_token"
    assert account_id == "123456789"


def test_get_credentials_missing_raises(monkeypatch):
    monkeypatch.delenv("INSTAGRAM_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("INSTAGRAM_ACCOUNT_ID", raising=False)

    with patch("upload_to_instagram.load_env_file"):
        with pytest.raises(ValueError, match="Missing Instagram Access Token"):
            get_credentials()


def test_discover_pending_videos_sorting(tmp_path):
    # Create files out of order
    f_today = tmp_path / "video_2026-10-25.mp4"
    f_old1 = tmp_path / "video_2026-10-22.mp4"
    f_old2 = tmp_path / "video_2026-10-24.mp4"
    f_other = tmp_path / "some_other.mp4"

    f_today.touch()
    f_old1.touch()
    f_old2.touch()
    f_other.touch()

    pending = discover_pending_videos(tmp_path)
    assert len(pending) == 3

    # Assert strictly chronological order (oldest first)
    assert pending[0][0].name == "video_2026-10-22.mp4"
    assert pending[1][0].name == "video_2026-10-24.mp4"
    assert pending[2][0].name == "video_2026-10-25.mp4"


def test_upload_to_public_host_mocked(tmp_path):
    dummy_video = tmp_path / "video_test.mp4"
    dummy_video.write_bytes(b"dummy video data")

    mock_resp = MagicMock()
    mock_resp.read.return_value = b"https://files.catbox.moe/abc123.mp4\n"
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        url = upload_to_public_host(dummy_video)
        assert url == "https://files.catbox.moe/abc123.mp4"


def test_create_reel_container_mocked():
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"id": "container_999"}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        cid = create_reel_container("acc_1", "tok_1", "https://mock.url/v.mp4", "mock caption")
        assert cid == "container_999"


def test_wait_for_container_ready_success():
    resp_in_progress = MagicMock()
    resp_in_progress.read.return_value = json.dumps({"status_code": "IN_PROGRESS"}).encode("utf-8")
    resp_in_progress.__enter__.return_value = resp_in_progress

    resp_finished = MagicMock()
    resp_finished.read.return_value = json.dumps({"status_code": "FINISHED"}).encode("utf-8")
    resp_finished.__enter__.return_value = resp_finished

    with patch("urllib.request.urlopen", side_effect=[resp_in_progress, resp_finished]), \
         patch("time.sleep", return_value=None):
        result = wait_for_container_ready("container_999", "tok_1", timeout_seconds=10, poll_interval=0.01)
        assert result is True


def test_wait_for_container_ready_error():
    resp_error = MagicMock()
    resp_error.read.return_value = json.dumps({"status_code": "ERROR"}).encode("utf-8")
    resp_error.__enter__.return_value = resp_error

    with patch("urllib.request.urlopen", return_value=resp_error), \
         patch("time.sleep", return_value=None):
        with pytest.raises(RuntimeError, match="Container processing failed"):
            wait_for_container_ready("container_999", "tok_1", timeout_seconds=10, poll_interval=0.01)


def test_publish_reel_container_mocked():
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"id": "media_post_777"}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        mid = publish_reel_container("acc_1", "tok_1", "container_999")
        assert mid == "media_post_777"


def test_process_video_upload_deletes_on_success(tmp_path):
    test_file = tmp_path / "video_2026-10-25.mp4"
    test_file.write_bytes(b"content")

    with patch("upload_to_instagram.upload_to_public_host", return_value="https://files.catbox.moe/abc.mp4"), \
         patch("upload_to_instagram.create_reel_container", return_value="container_123"), \
         patch("upload_to_instagram.wait_for_container_ready", return_value=True), \
         patch("upload_to_instagram.publish_reel_container", return_value="media_456"):

        media_id = process_video_upload(
            video_path=test_file,
            video_date=datetime(2026, 10, 25),
            account_id="acc_1",
            access_token="tok_1",
            caption="test",
            dry_run=False
        )

        assert media_id == "media_456"
        # File must be deleted on success!
        assert not test_file.exists()


def test_process_video_upload_preserves_file_on_failure(tmp_path):
    test_file = tmp_path / "video_2026-10-25.mp4"
    test_file.write_bytes(b"content")

    with patch("upload_to_instagram.upload_to_public_host", return_value="https://files.catbox.moe/abc.mp4"), \
         patch("upload_to_instagram.create_reel_container", side_effect=RuntimeError("API failed")):

        with pytest.raises(RuntimeError, match="API failed"):
            process_video_upload(
                video_path=test_file,
                video_date=datetime(2026, 10, 25),
                account_id="acc_1",
                access_token="tok_1",
                caption="test",
                dry_run=False
            )

        # File must still exist when upload fails!
        assert test_file.exists()


def test_process_video_upload_dry_run_preserves_file(tmp_path):
    test_file = tmp_path / "video_2026-10-25.mp4"
    test_file.write_bytes(b"content")

    with patch("upload_to_instagram.upload_to_public_host", return_value="https://files.catbox.moe/abc.mp4"), \
         patch("upload_to_instagram.create_reel_container", return_value="container_123"), \
         patch("upload_to_instagram.wait_for_container_ready", return_value=True), \
         patch("upload_to_instagram.publish_reel_container") as mock_publish:

        media_id = process_video_upload(
            video_path=test_file,
            video_date=datetime(2026, 10, 25),
            account_id="acc_1",
            access_token="tok_1",
            caption="test",
            dry_run=True
        )

        assert media_id is None
        mock_publish.assert_not_called()
        # File must NOT be deleted in dry-run mode
        assert test_file.exists()
