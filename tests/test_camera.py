"""Tests for camera module."""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Mock picamera2 before importing Camera to allow
# the module to be tested on non-RPi systems
mock_picamera2_module = MagicMock()
mock_picamera2_module.Picamera2 = MagicMock()
mock_picamera2_module.H264Encoder = MagicMock()
mock_picamera2_module.MJPEGEncoder = MagicMock()

# Mock encoders module
mock_encoders = MagicMock()
mock_encoders.H264Encoder = MagicMock()
mock_encoders.MJPEGEncoder = MagicMock()
mock_picamera2_module.encoders = mock_encoders

sys.modules["picamera2"] = mock_picamera2_module
sys.modules["picamera2.encoders"] = mock_encoders

from nomon.camera import Camera  # noqa: E402


class TestCameraInitialization:
    """Tests for camera initialization."""

    @patch("nomon.camera.Picamera2")
    def test_camera_init_defaults(self, mock_picamera2):
        """Test camera initialization with defaults."""
        mock_picamera2.return_value = MagicMock()
        camera = Camera()

        assert camera.camera_index == 0
        assert camera.width == 1280
        assert camera.height == 720
        assert camera.fps == 30
        assert camera.encoder == "h264"
        assert camera.directory == Path.cwd()
        assert camera._is_recording is False

    @patch("nomon.camera.Picamera2")
    def test_camera_init_custom_params(self, mock_picamera2):
        """Test camera initialization with custom params."""
        mock_picamera2.return_value = MagicMock()
        camera = Camera(
            camera_index=1,
            width=1920,
            height=1080,
            fps=15,
            encoder="mjpeg",
            directory="/tmp/videos",
        )

        assert camera.camera_index == 1
        assert camera.width == 1920
        assert camera.height == 1080
        assert camera.fps == 15
        assert camera.encoder == "mjpeg"
        assert camera.directory == Path("/tmp/videos")

    @patch("nomon.camera.Picamera2")
    def test_camera_init_failure(self, mock_picamera2):
        """Test camera initialization failure."""
        mock_picamera2.side_effect = Exception("Camera not found")

        with pytest.raises(RuntimeError):
            Camera()

    @patch("nomon.camera.Picamera2")
    def test_camera_init_invalid_encoder(
        self,
        mock_picamera2,
    ):
        """Test camera initialization with invalid encoder."""
        mock_picamera2.return_value = MagicMock()

        with pytest.raises(ValueError):
            Camera(encoder="invalid")

    @patch("nomon.camera.Picamera2")
    def test_camera_repr(self, mock_picamera2):
        """Test camera string representation."""
        mock_picamera2.return_value = MagicMock()
        camera = Camera(
            camera_index=1,
            width=1920,
            height=1080,
            encoder="mjpeg",
        )

        repr_str = repr(camera)
        assert "1" in repr_str
        assert "1920" in repr_str
        assert "1080" in repr_str
        assert "mjpeg" in repr_str


class TestImageCapture:
    """Tests for image capture functionality."""

    @patch("nomon.camera.Picamera2")
    def test_capture_image_success(self, mock_picamera2):
        """Test successful image capture."""
        mock_cam = MagicMock()
        mock_picamera2.return_value = mock_cam
        mock_cam.create_still_configuration.return_value = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            camera = Camera(directory=tmpdir)
            camera.capture_image("test.jpg")

            mock_cam.start.assert_called()
            mock_cam.capture_file.assert_called()
            mock_cam.stop.assert_called()

    @patch("nomon.camera.Picamera2")
    def test_capture_image_not_initialized(self, mock_picamera2):
        """Test capture when camera not initialized."""
        mock_picamera2.return_value = MagicMock()
        camera = Camera()
        camera._camera = None

        with pytest.raises(RuntimeError):
            camera.capture_image("test.jpg")

    @patch("nomon.camera.Picamera2")
    def test_capture_image_rejects_paths(self, mock_picamera2):
        """Test that paths with separators are rejected."""
        mock_picamera2.return_value = MagicMock()
        camera = Camera()

        with pytest.raises(ValueError, match="path separators"):
            camera.capture_image("subdir/test.jpg")

    @patch("nomon.camera.Picamera2")
    def test_capture_image_rejects_absolute_paths(
        self,
        mock_picamera2,
    ):
        """Test that absolute paths are rejected."""
        mock_picamera2.return_value = MagicMock()
        camera = Camera()

        # Absolute paths are rejected (either as absolute
        # or path separator violation)
        with pytest.raises(ValueError):
            camera.capture_image("/etc/passwd")


class TestVideoRecording:
    """Tests for video recording functionality."""

    @patch("nomon.camera.H264Encoder")
    @patch("nomon.camera.Picamera2")
    def test_start_recording_h264(
        self,
        mock_picamera2,
        mock_h264,
    ):
        """Test successful recording with H264."""
        mock_cam = MagicMock()
        mock_picamera2.return_value = mock_cam
        mock_cam.create_video_configuration.return_value = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            camera = Camera(encoder="h264", directory=tmpdir)
            camera.start_recording("test.mp4")

            assert camera._is_recording is True
            mock_cam.start.assert_called()
            mock_cam.start_recording.assert_called()

    @patch("nomon.camera.MJPEGEncoder")
    @patch("nomon.camera.Picamera2")
    def test_start_recording_mjpeg(
        self,
        mock_picamera2,
        mock_mjpeg,
    ):
        """Test successful recording with MJPEG."""
        mock_cam = MagicMock()
        mock_picamera2.return_value = mock_cam
        mock_cam.create_video_configuration.return_value = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            camera = Camera(encoder="mjpeg", directory=tmpdir)
            camera.start_recording("test.mp4")

            assert camera._is_recording is True
            mock_cam.start.assert_called()
            mock_cam.start_recording.assert_called()

    @patch("nomon.camera.Picamera2")
    def test_stop_recording_success(self, mock_picamera2):
        """Test successful recording stop."""
        mock_cam = MagicMock()
        mock_picamera2.return_value = mock_cam
        mock_cam.create_video_configuration.return_value = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("nomon.camera.H264Encoder"):
                camera = Camera(directory=tmpdir)
                camera.start_recording("test.mp4")
                camera.stop_recording()

            assert camera._is_recording is False
            mock_cam.stop_recording.assert_called()
            mock_cam.stop.assert_called()

    @patch("nomon.camera.Picamera2")
    def test_stop_recording_when_not_recording(
        self,
        mock_picamera2,
    ):
        """Test stop recording when not recording."""
        mock_picamera2.return_value = MagicMock()
        camera = Camera()

        with pytest.raises(RuntimeError):
            camera.stop_recording()

    @patch("nomon.camera.H264Encoder")
    @patch("nomon.camera.Picamera2")
    def test_double_start_recording(
        self,
        mock_picamera2,
        mock_h264,
    ):
        """Test starting recording twice."""
        mock_cam = MagicMock()
        mock_picamera2.return_value = mock_cam
        mock_cam.create_video_configuration.return_value = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            camera = Camera(directory=tmpdir)
            camera.start_recording("test.mp4")

            with pytest.raises(RuntimeError):
                camera.start_recording("test2.mp4")

    @patch("nomon.camera.Picamera2")
    def test_start_recording_rejects_paths(
        self,
        mock_picamera2,
    ):
        """Test that paths with separators are rejected."""
        mock_picamera2.return_value = MagicMock()
        camera = Camera()

        with pytest.raises(ValueError, match="path separators"):
            camera.start_recording("subdir/test.mp4")

    @patch("nomon.camera.Picamera2")
    def test_start_recording_rejects_traversal(
        self,
        mock_picamera2,
    ):
        """Test that traversal attempts are rejected."""
        mock_picamera2.return_value = MagicMock()
        camera = Camera()

        with pytest.raises(ValueError, match="\\.\\."):
            camera.start_recording("../../../etc/passwd")


class TestContextManager:
    """Tests for context manager functionality."""

    @patch("nomon.camera.Picamera2")
    def test_context_manager_success(self, mock_picamera2):
        """Test using camera as context manager."""
        mock_cam = MagicMock()
        mock_picamera2.return_value = mock_cam

        with Camera() as camera:
            assert camera is not None

        mock_cam.close.assert_called()

    @patch("nomon.camera.H264Encoder")
    @patch("nomon.camera.Picamera2")
    def test_context_manager_with_recording(
        self,
        mock_picamera2,
        mock_h264,
    ):
        """Test context manager with active recording."""
        mock_cam = MagicMock()
        mock_picamera2.return_value = mock_cam
        mock_cam.create_video_configuration.return_value = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            with Camera(directory=tmpdir) as camera:
                camera.start_recording("test.mp4")

            # Cleanup should have stopped recording
            assert not camera._is_recording


class TestFrameGenerator:
    """Tests for frame streaming functionality."""

    @patch("nomon.camera.Picamera2")
    def test_frame_generator_initialization(
        self,
        mock_picamera2,
    ):
        """Test that generator initializes camera."""
        mock_cam = MagicMock()
        mock_picamera2.return_value = mock_cam
        mock_cam.create_video_configuration.return_value = {}

        mock_frame = MagicMock()
        mock_frame.tobytes.return_value = b"frame_data"
        mock_cam.capture_buffer.return_value = mock_frame

        camera = Camera()
        gen = camera.get_frame_generator()

        # Get first frame
        next(gen)

        mock_cam.start.assert_called()
        mock_cam.create_video_configuration.assert_called()

    @patch("nomon.camera.Picamera2")
    def test_frame_generator_not_initialized(
        self,
        mock_picamera2,
    ):
        """Test generator when camera not initialized."""
        mock_picamera2.return_value = MagicMock()
        camera = Camera()
        camera._camera = None

        with pytest.raises(RuntimeError):
            next(camera.get_frame_generator())


class TestJPEGFrameGenerator:
    """Tests for JPEG frame streaming functionality."""

    @patch("nomon.camera.Picamera2")
    def test_jpeg_frame_generator_initialization(
        self,
        mock_picamera2,
    ):
        """Test that JPEG generator initializes camera."""
        mock_cam = MagicMock()
        mock_picamera2.return_value = mock_cam
        mock_cam.create_still_configuration.return_value = {}

        # Mock capture_file to write JPEG data to buffer
        def mock_capture(buffer, format=None):
            buffer.write(b"\xff\xd8\xff\xe0")  # JPEG SOI+APP0 marker

        mock_cam.capture_file.side_effect = mock_capture

        camera = Camera()
        gen = camera.get_jpeg_frame_generator()

        # Get first frame
        frame = next(gen)

        assert isinstance(frame, bytes)
        assert len(frame) > 0
        mock_cam.start.assert_called()
        mock_cam.create_still_configuration.assert_called()

    @patch("nomon.camera.Picamera2")
    def test_jpeg_frame_generator_not_initialized(
        self,
        mock_picamera2,
    ):
        """Test JPEG generator when camera not initialized."""
        mock_picamera2.return_value = MagicMock()
        camera = Camera()
        camera._camera = None

        with pytest.raises(RuntimeError):
            next(camera.get_jpeg_frame_generator())

    @patch("nomon.camera.Picamera2")
    def test_jpeg_frame_generator_error_handling(
        self,
        mock_picamera2,
    ):
        """Test JPEG generator error handling."""
        mock_cam = MagicMock()
        mock_picamera2.return_value = mock_cam
        mock_cam.create_still_configuration.return_value = {}
        mock_cam.capture_file.side_effect = OSError("Capture failed")

        camera = Camera()
        gen = camera.get_jpeg_frame_generator()

        with pytest.raises(RuntimeError, match="JPEG streaming failed"):
            next(gen)
