"""Production integration and security tests for FastAPI web endpoints."""
import io
import pytest
from fastapi.testclient import TestClient
from server import app

client = TestClient(app)


def test_index_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "9:16 Portrait Video Studio" in response.text


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code in (200, 503)
    data = response.json()
    assert "status" in data
    assert "uptime_seconds" in data
    assert "ffmpeg_available" in data
    assert "ffprobe_available" in data


def test_api_info_endpoint():
    response = client.get("/api/info")
    assert response.status_code == 200
    data = response.json()
    assert "gradient_presets" in data
    assert "templates" in data
    assert "max_duration" in data
    assert "min_duration" in data
    assert "sunset" in data["gradient_presets"]
    assert "modern_card" in data["templates"]


def test_path_traversal_prevention():
    # Attempting traversal or invalid filenames on /outputs/
    malicious_filenames = [
        "secret.mp4",
        "video_secret..mp4",
        "video_nonexistent.mp4",
        "random_non_existent.mp4",
        "video_invalid;rm -rf.mp4",
        "video_..%2F..%2Fetc.mp4",
    ]
    for fn in malicious_filenames:
        response = client.get(f"/outputs/{fn}")
        assert response.status_code in (400, 404)


def test_invalid_duration_validation():
    # Negative / too small
    res1 = client.post("/api/generate", data={"text": "Hello", "duration": "0.1"})
    assert res1.status_code == 400
    assert "Duration must be between" in res1.json()["detail"]

    # Too long
    res2 = client.post("/api/generate", data={"text": "Hello", "duration": "9999"})
    assert res2.status_code == 400
    assert "Duration must be between" in res2.json()["detail"]


def test_invalid_gradient_validation():
    res = client.post("/api/generate", data={"text": "Hello", "gradient": "non_existent_gradient"})
    assert res.status_code == 400
    assert "Invalid gradient preset" in res.json()["detail"]


def test_invalid_template_validation():
    res = client.post("/api/generate", data={"text": "Hello", "template": "non_existent_template"})
    assert res.status_code == 400
    assert "Invalid template" in res.json()["detail"]


def test_empty_text_validation():
    res = client.post("/api/generate", data={"text": "   "})
    assert res.status_code == 400
    assert "Text field cannot be empty" in res.json()["detail"]


def test_unsupported_file_extension():
    fake_exe = io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00")
    res = client.post(
        "/api/generate",
        data={"text": "Hello", "duration": "5"},
        files={"image": ("malicious.exe", fake_exe, "application/octet-stream")}
    )
    assert res.status_code == 400
    assert "Unsupported file extension" in res.json()["detail"]


def test_generate_endpoint_with_demo():
    response = client.post(
        "/api/generate",
        data={
            "text": "Web UI test headline",
            "gradient": "sunset",
            "bg_mode": "static",
            "template": "modern_card",
            "duration": "2.0",
            "use_demo": "true"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "video_url" in data
    assert data["filename"].endswith(".mp4")

    # Verify that the generated video can be retrieved
    video_res = client.get(data["video_url"])
    assert video_res.status_code == 200
    assert video_res.headers["content-type"] == "video/mp4"
