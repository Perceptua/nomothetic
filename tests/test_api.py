"""Tests for the HTTP REST API module.

Tests cover endpoint functionality, error handling, and CORS behavior.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from nomon.api import APIServer, create_app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def mock_camera():
    """Create a mock camera for testing."""
    camera = MagicMock()
    camera.width = 1280
    camera.height = 720
    camera.fps = 30
    camera.encoder = "h264"
    camera._is_recording = False
    return camera


# ============================================================================
# Health & Status Endpoints
# ============================================================================


def test_health_check(client):
    """Test health check endpoint returns success."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "nomon-camera-api"
    assert "version" in data


def test_camera_status_without_camera(client):
    """Test camera status endpoint without initialized camera."""
    response = client.get("/api/camera/status")
    assert response.status_code == 500
    assert "not initialized" in response.json()["error"]


def test_camera_status_with_camera(client, mock_camera):
    """Test camera status endpoint returns current state."""
    import nomon.api

    nomon.api._camera = mock_camera

    response = client.get("/api/camera/status")
    assert response.status_code == 200
    data = response.json()
    assert data["camera_ready"] is True
    assert data["recording"] is False
    assert data["resolution"] == "1280x720"
    assert data["fps"] == 30
    assert data["encoder"] == "h264"
    assert "timestamp" in data

    # Cleanup
    nomon.api._camera = None


def test_camera_status_recording(client, mock_camera):
    """Test camera status reflects recording state."""
    import nomon.api

    mock_camera._is_recording = True
    nomon.api._camera = mock_camera

    response = client.get("/api/camera/status")
    assert response.status_code == 200
    assert response.json()["recording"] is True

    # Cleanup
    nomon.api._camera = None


# ============================================================================
# Image Capture Endpoints
# ============================================================================


def test_capture_image_success(client, mock_camera):
    """Test successful image capture."""
    import nomon.api

    nomon.api._camera = mock_camera

    response = client.post(
        "/api/camera/capture",
        json={"filename": "test.jpg"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["filename"] == "test.jpg"
    assert "timestamp" in data
    mock_camera.capture_image.assert_called_once_with("test.jpg")

    # Cleanup
    nomon.api._camera = None


def test_capture_image_invalid_filename(client, mock_camera):
    """Test capture with invalid filename raises error."""
    import nomon.api

    mock_camera.capture_image.side_effect = ValueError("Invalid filename")
    nomon.api._camera = mock_camera

    response = client.post(
        "/api/camera/capture",
        json={"filename": "../etc/passwd"},
    )
    assert response.status_code == 400
    assert "Invalid filename" in response.json()["error"]

    # Cleanup
    nomon.api._camera = None


def test_capture_image_camera_error(client, mock_camera):
    """Test capture with camera error."""
    import nomon.api

    mock_camera.capture_image.side_effect = RuntimeError("Camera failed")
    nomon.api._camera = mock_camera

    response = client.post(
        "/api/camera/capture",
        json={"filename": "photo.jpg"},
    )
    assert response.status_code == 500
    assert "Camera failed" in response.json()["error"]

    # Cleanup
    nomon.api._camera = None


def test_capture_without_camera(client):
    """Test capture endpoint without initialized camera."""
    response = client.post(
        "/api/camera/capture",
        json={"filename": "test.jpg"},
    )
    assert response.status_code == 500
    assert "not initialized" in response.json()["error"]


# ============================================================================
# Video Recording Endpoints
# ============================================================================


def test_record_start_success(client, mock_camera):
    """Test successful recording start."""
    import nomon.api

    nomon.api._camera = mock_camera

    response = client.post(
        "/api/camera/record/start",
        json={"filename": "video.mp4"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["filename"] == "video.mp4"
    assert "timestamp" in data
    mock_camera.start_recording.assert_called_once_with("video.mp4")

    # Cleanup
    nomon.api._camera = None


def test_record_start_with_encoder(client, mock_camera):
    """Test recording start with encoder specification."""
    import nomon.api

    nomon.api._camera = mock_camera

    response = client.post(
        "/api/camera/record/start",
        json={"filename": "video.mp4", "encoder": "mjpeg"},
    )
    assert response.status_code == 200
    # Encoder should be updated
    assert mock_camera.encoder == "mjpeg"

    # Cleanup
    nomon.api._camera = None


def test_record_start_already_recording(client, mock_camera):
    """Test recording start when already recording."""
    import nomon.api

    mock_camera._is_recording = True
    nomon.api._camera = mock_camera

    response = client.post(
        "/api/camera/record/start",
        json={"filename": "video.mp4"},
    )
    assert response.status_code == 409
    assert "Recording already in progress" in response.json()["error"]

    # Cleanup
    nomon.api._camera = None


def test_record_start_invalid_filename(client, mock_camera):
    """Test recording start with invalid filename."""
    import nomon.api

    mock_camera.start_recording.side_effect = ValueError("Invalid filename")
    nomon.api._camera = mock_camera

    response = client.post(
        "/api/camera/record/start",
        json={"filename": "../etc/passwd"},
    )
    assert response.status_code == 400

    # Cleanup
    nomon.api._camera = None


def test_record_start_without_camera(client):
    """Test record start without initialized camera."""
    response = client.post(
        "/api/camera/record/start",
        json={"filename": "video.mp4"},
    )
    assert response.status_code == 500
    assert "not initialized" in response.json()["error"]


def test_record_stop_success(client, mock_camera):
    """Test successful recording stop."""
    import nomon.api

    mock_camera._is_recording = True
    nomon.api._camera = mock_camera

    response = client.post("/api/camera/record/stop")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "timestamp" in data
    mock_camera.stop_recording.assert_called_once()

    # Cleanup
    nomon.api._camera = None


def test_record_stop_not_recording(client, mock_camera):
    """Test recording stop when not recording."""
    import nomon.api

    nomon.api._camera = mock_camera

    response = client.post("/api/camera/record/stop")
    assert response.status_code == 409
    assert "No recording in progress" in response.json()["error"]

    # Cleanup
    nomon.api._camera = None


def test_record_stop_camera_error(client, mock_camera):
    """Test recording stop with camera error."""
    import nomon.api

    mock_camera._is_recording = True
    mock_camera.stop_recording.side_effect = RuntimeError("Stop failed")
    nomon.api._camera = mock_camera

    response = client.post("/api/camera/record/stop")
    assert response.status_code == 500
    assert "Stop failed" in response.json()["error"]

    # Cleanup
    nomon.api._camera = None


def test_record_stop_without_camera(client):
    """Test record stop without initialized camera."""
    response = client.post("/api/camera/record/stop")
    assert response.status_code == 500
    assert "not initialized" in response.json()["error"]


# ============================================================================
# CORS Headers
# ============================================================================


def test_cors_middleware_configured(client):
    """Test that middleware is configured."""
    app = client.app
    # Check that app has middleware
    assert len(app.user_middleware) > 0


# ============================================================================
# API Server Configuration
# ============================================================================


def test_api_server_initialization():
    """Test APIServer initialization with defaults."""
    server = APIServer()
    assert server.host == "127.0.0.1"
    assert server.port == 8443
    assert server.use_ssl is True


def test_api_server_custom_host_port():
    """Test APIServer with custom host and port."""
    server = APIServer(host="0.0.0.0", port=9000)
    assert server.host == "0.0.0.0"
    assert server.port == 9000


def test_api_server_invalid_port():
    """Test APIServer rejects invalid ports."""
    with pytest.raises(ValueError, match="Invalid port"):
        APIServer(port=0)

    with pytest.raises(ValueError, match="Invalid port"):
        APIServer(port=70000)


def test_api_server_get_config():
    """Test APIServer configuration generation."""
    server = APIServer(host="localhost", port=8000, use_ssl=False)
    config = server.get_config()
    assert config["host"] == "localhost"
    assert config["port"] == 8000
    assert "ssl_certfile" not in config


def test_api_server_get_config_with_ssl():
    """Test APIServer configuration with SSL."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        server = APIServer(port=8443, use_ssl=True, cert_dir=Path(tmpdir))
        config = server.get_config()
        assert "ssl_certfile" in config
        assert "ssl_keyfile" in config


# ============================================================================
# Request/Response Models
# ============================================================================


def test_capture_request_model():
    """Test CaptureRequest validation."""
    from nomon.api import CaptureRequest

    req = CaptureRequest(filename="test.jpg")
    assert req.filename == "test.jpg"


def test_record_request_model():
    """Test RecordRequest validation."""
    from nomon.api import RecordRequest

    req = RecordRequest(filename="video.mp4")
    assert req.filename == "video.mp4"
    assert req.encoder == "h264"

    req2 = RecordRequest(filename="video.mp4", encoder="mjpeg")
    assert req2.encoder == "mjpeg"


def test_camera_status_model():
    """Test CameraStatus model."""
    from nomon.api import CameraStatus

    status = CameraStatus(
        camera_ready=True,
        recording=False,
        resolution="1280x720",
        fps=30,
        encoder="h264",
        timestamp="2024-01-01T00:00:00",
    )
    assert status.camera_ready is True
    assert status.recording is False


# ============================================================================
# System / OTA Endpoints
# ============================================================================


@pytest.fixture
def mock_updater():
    """Return a minimal mock UpdateManager."""
    from datetime import datetime, timezone

    from nomon.updater import UpdateManager

    mgr = MagicMock(spec=UpdateManager)
    mgr._lock = __import__("threading").Lock()
    mgr.update_available = False
    mgr.latest_manifest = None
    mgr.last_checked = datetime(2026, 3, 4, 12, 0, 0, tzinfo=timezone.utc)
    return mgr


def test_version_endpoint_returns_version(client):
    """GET /api/system/version returns version, git_hash, and timestamp."""
    from nomon.updater import UpdateManager

    with patch.object(UpdateManager, "_get_git_hash", return_value="abc123"):
        response = client.get("/api/system/version")

    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "git_hash" in data
    assert "timestamp" in data
    assert data["git_hash"] == "abc123"


def test_version_endpoint_version_matches_package(client):
    """GET /api/system/version version field matches nomon.__version__."""
    import nomon
    from nomon.updater import UpdateManager

    with patch.object(UpdateManager, "_get_git_hash", return_value="abc"):
        response = client.get("/api/system/version")

    assert response.json()["version"] == nomon.__version__


def test_update_status_without_updater(client):
    """GET /api/system/update/status returns sensible defaults when no updater configured."""
    import nomon.api

    nomon.api._updater = None
    response = client.get("/api/system/update/status")
    assert response.status_code == 200
    data = response.json()
    assert data["update_available"] is False
    assert data["latest_version"] is None
    assert data["last_checked"] is None


def test_update_status_no_update_available(client, mock_updater):
    """GET /api/system/update/status returns False when no update is queued."""
    import nomon.api

    mock_updater.update_available = False
    mock_updater.latest_manifest = None
    nomon.api._updater = mock_updater

    response = client.get("/api/system/update/status")
    assert response.status_code == 200
    data = response.json()
    assert data["update_available"] is False
    assert data["latest_version"] is None

    nomon.api._updater = None


def test_update_status_update_available(client, mock_updater):
    """GET /api/system/update/status reflects available update."""
    import nomon.api

    mock_updater.update_available = True
    mock_updater.latest_manifest = {"version": "99.0.0"}
    nomon.api._updater = mock_updater

    response = client.get("/api/system/update/status")
    assert response.status_code == 200
    data = response.json()
    assert data["update_available"] is True
    assert data["latest_version"] == "99.0.0"

    nomon.api._updater = None


def test_apply_update_without_updater_returns_503(client):
    """POST /api/system/update/apply returns 503 when updater not configured."""
    import nomon.api

    nomon.api._updater = None
    response = client.post("/api/system/update/apply")
    assert response.status_code == 503
    assert "NOMON_UPDATE_MANIFEST_URL" in response.json()["error"]


def test_apply_update_no_update_available_returns_503(client, mock_updater):
    """POST /api/system/update/apply returns 503 when no update is queued."""
    import nomon.api

    mock_updater.update_available = False
    nomon.api._updater = mock_updater

    response = client.post("/api/system/update/apply")
    assert response.status_code == 503

    nomon.api._updater = None


def test_apply_update_success(client, mock_updater):
    """POST /api/system/update/apply returns 200 on success."""
    import nomon.api

    mock_updater.update_available = True
    mock_updater.latest_manifest = {"version": "1.1.0", "git_sha": "abc123"}
    mock_updater.apply_update.return_value = True
    nomon.api._updater = mock_updater

    response = client.post("/api/system/update/apply")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "timestamp" in data

    nomon.api._updater = None


def test_apply_update_409_when_recording(client, mock_updater):
    """POST /api/system/update/apply returns 409 when camera is recording."""
    import nomon.api

    mock_updater.update_available = True
    mock_updater.latest_manifest = {"version": "1.1.0", "git_sha": "abc123"}
    mock_updater.apply_update.side_effect = RuntimeError("recording in progress")
    nomon.api._updater = mock_updater

    response = client.post("/api/system/update/apply")
    assert response.status_code == 409

    nomon.api._updater = None


def test_apply_update_500_on_failure(client, mock_updater):
    """POST /api/system/update/apply returns 500 on update error."""
    import nomon.api

    mock_updater.update_available = True
    mock_updater.latest_manifest = {"version": "1.1.0", "git_sha": "abc123"}
    mock_updater.apply_update.side_effect = RuntimeError("git fetch failed")
    nomon.api._updater = mock_updater

    response = client.post("/api/system/update/apply")
    assert response.status_code == 500

    nomon.api._updater = None


def test_apply_update_503_on_no_update_available_runtime_error(client, mock_updater):
    """POST /api/system/update/apply returns 503 when apply_update raises 'no update available'."""
    import nomon.api

    mock_updater.update_available = True
    mock_updater.latest_manifest = {"version": "1.1.0", "git_sha": "abc123"}
    mock_updater.apply_update.side_effect = RuntimeError("No update available. Call check_for_update() first.")
    nomon.api._updater = mock_updater

    response = client.post("/api/system/update/apply")
    assert response.status_code == 503

    nomon.api._updater = None


def test_apply_update_503_on_unknown_rollback_point(client, mock_updater):
    """POST /api/system/update/apply returns 503 when apply_update raises 'rollback point' error."""
    import nomon.api

    mock_updater.update_available = True
    mock_updater.latest_manifest = {"version": "1.1.0", "git_sha": "abc123"}
    mock_updater.apply_update.side_effect = RuntimeError("Cannot apply update without a valid rollback point.")
    nomon.api._updater = mock_updater

    response = client.post("/api/system/update/apply")
    assert response.status_code == 503

    nomon.api._updater = None

