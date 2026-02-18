# nomon - Setup & Progress

## Project Overview
Scripts for Raspberry Pi microcontroller & peripherals with HAT (Hardware Attached on Top) module support.

---

## ✅ Setup Completed

### Core Configuration Files
- **pyproject.toml** - Complete project metadata, dependencies, and tool configurations
  - Python >= 3.8 support
  - Configured for setuptools build system
  - Tool configs for black, ruff, mypy, pytest

### Dependency Management
- **requirements.txt** - Production dependencies
  - gpiozero >= 2.0 (high-level GPIO abstraction)
  - pigpio >= 1.78 (low-level GPIO daemon)
  - smbus2 >= 0.4.1 (I2C communication)
  - pyserial >= 3.5 (serial communication)
  - spidev >= 3.5 (conditional on Linux only)

- **requirements-dev.txt** - Development dependencies
  - pytest + pytest-cov (testing)
  - black (code formatting)
  - ruff (linting)
  - mypy (type checking)
  - sphinx (documentation)

### Project Structure
- **tests/** directory with example test
- **src/nomon/__init__.py** - Package initialization with version metadata
- **Makefile** - Common development commands:
  - `make install-dev` - Install with dev dependencies
  - `make test` - Run tests with coverage
  - `make lint` - Check code style
  - `make format` - Format code
  - `make type-check` - Run type checking
  - `make clean` - Remove generated files

### Development Tools
- **.editorconfig** - Consistent editor formatting
- **MANIFEST.in** - Package distribution metadata
- **.gitignore** - Already configured for Python projects

### Environment Setup
- Dependencies installed and verified (`pip install -e ".[dev]"` successful)
- spidev configured as Linux-only (avoids Visual Studio compilation on Windows)

---

---

## 🎯 Current Focus

### Phase 1: Raspberry Pi Camera Module ✅ COMPLETE

**Camera Implementation** (`src/nomon/camera.py`)
- ✅ Still image capture via `capture_image(filename)`
- ✅ Video recording via `start_recording(filename)` / `stop_recording()`
- ✅ Live streaming via `get_frame_generator()` 
- ✅ Encoder selection (H264 @ 5Mbps or MJPEG)
- ✅ Context manager support for clean resource management
- ✅ Full type hints and docstrings
- ✅ 20 comprehensive tests (all passing)

**Hardware Integration**
- ✅ OV5647 sensor specifications discovered and documented
  - Default video: 1280x720 @ 30 fps (practical balance)
  - Maximum resolution: 2592x1944 @ 15.63 fps
  - Dual encoder support: H264, MJPEG
- ✅ Hardware discovery guide in CAMERA_DISCOVERY.md

**Security Hardening**
- ✅ Filename-only validation (no path-like components allowed)
- ✅ Path traversal protection (blocks `..`, `./`, absolute paths)
- ✅ Hidden file protection (rejects filenames starting with `.`)
- ✅ Directory containment enforcement (all files saved to configured directory)
- ✅ Security tests validating attack prevention

**API Design**
- Constructor: `Camera(camera_index, width, height, fps, encoder, directory)`
  - Defaults optimized for OV5647: 1280x720 @ 30fps H264
  - Optional directory parameter for file storage control
- Methods accept plain filenames only: `capture_image("photo.jpg")`
- Raises `ValueError` on invalid filename attempts
- Comprehensive error messages for debugging

**Test Coverage** (20 tests)
- Initialization with defaults and custom parameters
- Image capture success and error cases
- Video recording with H264 and MJPEG encoders
- Double-start recording prevention
- Context manager cleanup
- Frame generator functionality
- Path traversal attack prevention
- Filename validation (separators, absolute paths, traversal)

### Phase 1.5: Camera Web Streaming ✅ COMPLETE

**Implementation Complete**
- ✅ Architecture: MJPEG over HTTP (multipart/x-mixed-replace)
- ✅ Optional dependency strategy: Flask in `[web]` optional group
- ✅ API design: `StreamServer` class with `start()` and `start_background()` methods
- ✅ Code implementation with full type hints and docstrings
- ✅ 14 comprehensive tests (all passing)
- ✅ HTML viewer page with responsive CSS
- ✅ Documentation and usage examples in SETUP.md

**StreamServer Class** (`src/nomon/streaming.py`)
- Access at `http://localhost:8000` (default, configurable)
- Endpoints:
  - `GET /` - HTML page with live stream viewer
  - `GET /stream` - MJPEG stream (multipart/x-mixed-replace)
- Thread-safe frame sharing from Camera to HTTP response
- Constructor parameters: host, port, camera_index, width, height, fps, encoder
- Full type hints and docstrings
- Security: localhost binding by default, port validation
- Methods:
  - `start()` - Run server (blocking)
  - `start_background()` - Run server in daemon thread
  - `close()` - Clean up camera resources

**HTML Viewer Page**
- Simple HTML with embedded CSS styling
- `<img>` tag pointed to `/stream` endpoint for continuous playback
- Displays camera resolution, frame rate, and encoder type
- Responsive layout for mobile and desktop viewing
- Dark theme for comfortable streaming experience

**Test Coverage** (14 tests)
- Server initialization with defaults and custom parameters
- Port validation (valid range 1-65535)
- Flask availability check (RuntimeError when not installed)
- Route registration (/ and /stream endpoints)
- HTML template rendering with correct parameters
- MJPEG stream endpoint configuration (multipart/x-mixed-replace mimetype)
- Server lifecycle (start, background thread, close)
- Camera integration and cleanup
- Debug mode handling

**Dependencies**
- Flask >= 2.0 in `[web]` optional dependencies
- Installation: `pip install nomon[web]` or `uv add ".[web]"`
- Not required for core camera functionality

**Rationale**
- MJPEG chosen for compatibility and simplicity:
  - Works in any browser without plugins or external libraries
  - No transcoding needed (Camera.get_frame_generator provides frames)
  - Simple multipart/x-mixed-replace HTTP protocol
  - Suitable for LAN verification on local network
- Flask chosen for minimal overhead:
  - Single-purpose streaming server (two endpoints)
  - No complex configuration required
  - Cross-platform (development on Windows/Mac, production on RPi)
  - Optional dependency keeps nomon lightweight for users who don't need streaming

### Phase 2: Remote Microcontroller Operations ✅ COMPLETE

**Communication Protocol Foundation** (`src/nomon/protocol.py`)

**Protocol Design**
- ✅ JSON-based message protocol (newline-delimited)
- ✅ Three message types: CommandMessage, ResponseMessage, NotificationMessage
- ✅ UUID-based request/response matching
- ✅ Transport-agnostic (works over TCP, HTTP, WebSocket, etc.)
- ✅ Mobile and web-friendly

**Message Types**
- `CommandMessage` - Client requests to execute camera operations
  - Fields: command, params, msg_id
  - Commands: capture_image, start_recording, stop_recording, get_status
- `ResponseMessage` - Server responses with result or error
  - Fields: status (success/error), data, error message, msg_id
- `NotificationMessage` - Future event notifications
  - Fields: event name, data, msg_id

**Message Serialization** (`MessageHandler`)
- ✅ JSON encoding/decoding with validation
- ✅ Message type detection and routing
- ✅ Round-trip serialization (serialize → parse → serialize)
- ✅ Comprehensive error messages for invalid messages

**Test Coverage** (27 tests)
- Message creation and validation
- Serialization and deserialization
- Round-trip encoding verification
- Error handling for malformed JSON/messages
- All transport-independent protocol concerns

**Why TCP Server/Client Were Removed**
- Not needed for your workflow: Tailscale + SSH for admin, HTTP for mobile
- Protocol contracts preserved for Phase 3 HTTP REST wrapper
- Cleaner codebase with less unused code
- Protocol abstraction remains reusable for any transport

**Documentation**
- ✅ Protocol specification and message contracts
- ✅ Usage examples and patterns
- ✅ Integration notes for Phase 3

### Phase 3: HTTP REST API & Authentication (Next)
- HTTP REST wrapper around Phase 2 protocol
- TLS/SSL encryption
- JWT token or API key authentication
- CORS support for web and mobile clients
- Mobile app ready

### Phase 4: HAT Control & Peripherals (Future)
- Identify specific HAT module(s)
- Implement driver/interface layers
- Sensor integration and actuator control

---

## 🚀 Getting Started

### Using the Camera Module
```python
from pathlib import Path
from nomon.camera import Camera

# Initialize with custom directory
camera = Camera(
    width=1280, 
    height=720, 
    fps=30, 
    encoder="h264",
    directory=Path("./videos")
)

# Capture still image (filename only, no paths)
camera.capture_image("photo.jpg")

# Record video
camera.start_recording("video.mp4")
# ... recording ...
camera.stop_recording()

# Stream frames
for frame in camera.get_frame_generator():
    process_frame(frame)

# Context manager for cleanup
with Camera() as cam:
    cam.capture_image("snap.jpg")
    # Automatic cleanup on exit
```

### Using the Web Streaming Server
```python
from nomon.streaming import StreamServer

# Start streaming server
server = StreamServer(
    host="localhost",
    port=8000,
    width=1280,
    height=720,
    fps=30,
    encoder="h264"
)

# Navigate to http://localhost:8000 in your browser
server.start()  # This blocks until server is stopped (Ctrl+C)
```

Or run in background:
```python
from nomon.streaming import StreamServer

server = StreamServer()
thread = server.start_background()

# ... do other work while server runs ...

server.close()  # Clean up when done
```

### Remote Camera Control (Phase 2 - Protocol Foundation Only)

The Phase 2 communication protocol (`CommandMessage`, `ResponseMessage`, etc.) is available for reference and serves as the contract for Phase 3's HTTP REST API.

The raw TCP server/client implementation was removed as they won't be used in your workflow:
- **Admin access** uses Tailscale + SSH
- **Mobile apps** will use HTTP REST API (Phase 3)
- **Local development** uses direct Python imports

Phase 3 will build the HTTP REST wrapper that implements these protocol message contracts.


```bash
# Install with dev dependencies (no web streaming)
uv add . --dev

# Or with pip
pip install -e ".[dev]"
```

### With Web Streaming Support
```bash
# Install with dev and web dependencies
uv add ".[dev,web]"

# Or with pip
pip install -e ".[dev,web]"
```

### Running Tests
```bash
make test           # Run with coverage report
pytest tests/ -v    # Verbose test output
```

### Code Quality
```bash
make format         # Format code with black & ruff
make lint           # Check code style
make type-check     # Type checking
```

### On Raspberry Pi
spidev and picamera2 will automatically install when dependencies are installed on Linux systems.

---

## 📝 Design Principles & Notes

**Keep this codebase minimal.** Let the standard library and imported packages do the heavy lifting. This repo should be focused on **interacting with a microcontroller & peripherals** rather than defining broad patterns for such interactions.

- Cross-platform development: Code works on Windows/Mac for testing, hardware-ready on RPi
- All tool configurations (black, ruff, mypy) are pre-configured in pyproject.toml
- Test infrastructure ready for unit and integration tests
- Security is built-in: filename validation prevents path traversal and directory escape attacks
- Camera module is production-ready and fully tested with 20 test cases
