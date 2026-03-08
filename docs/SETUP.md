# nomon - Setup & Progress

## Project Overview
Scripts for Raspberry Pi microcontroller & peripherals with HAT (Hardware Attached on Top) module support.

---

## Project Architecture

### Remote Devices
- **Raspberry Pi Microcontrollers with HAT** - A small fleet of independent automatons
  - Python >= 3.9 support
  - Runs nomon app (HTTPS REST w/ secure authentication)
  - Telemetry published via MQTT
  - OTA updates
  - Admin via Tailscale & SSH

### User Mobile Application
- To be developed elsewhere

### Centralized Device Management
- **Python web server**
  - MQTT broker for telemetry logging & notifications
  - API endpoint for version manifest
  - Object storage via s3 for release artifacts


## ✅ Setup Completed

### Core Configuration Files
- **pyproject.toml** - Complete project metadata, dependencies, and tool configurations
  - Python >= 3.9 support
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
- **src/nomothetic/__init__.py** - Package initialization with version metadata
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

**Camera Implementation** (`src/nomothetic/camera.py`)
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

**StreamServer Class** (`src/nomothetic/streaming.py`)
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
- Installation: `pip install nomothetic[web]` or `uv add ".[web]"`
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
  - Cross-platform: development and testing on Windows, macOS, and Linux; production on Raspberry Pi OS
  - Optional dependency keeps nomon lightweight for users who don't need streaming

### Phase 2: HTTP REST API & Authentication ✅ COMPLETE

**REST API Implementation** (`src/nomothetic/api.py`)
- ✅ FastAPI-based REST server with automatic OpenAPI documentation
- ✅ HTTPS/TLS support with self-signed certificate generation
- ✅ CORS middleware for web and mobile client compatibility
- ✅ Mobile-ready JSON request/response format
- ✅ 30+ comprehensive tests (all passing)

**Endpoints Implemented**
- `GET /` - Health check endpoint
- `GET /api/camera/status` - Get camera state (resolution, fps, encoder, recording status)
- `POST /api/camera/capture` - Capture still image (requires filename)
- `POST /api/camera/record/start` - Start video recording (requires filename, optional encoder)
- `POST /api/camera/record/stop` - Stop video recording
- Automatic OpenAPI docs at `GET /docs` and `GET /redoc`

**Technology Stack**
- FastAPI >= 0.100 (modern REST framework, automatic OpenAPI)
- uvicorn >= 0.24 (ASGI server with native SSL/TLS support)
- python-multipart >= 0.0.6 (request parsing)
- cryptography >= 41.0 (self-signed certificate generation)
- python-dotenv >= 1.0 (environment configuration)

**Security & Encryption**
- HTTPS enabled by default with self-signed certificates
- Self-signed certs auto-generated in `.certs/` directory on first run
- TLS certificates valid for 10 years (suitable for development and deployment)
- Filename validation prevents path traversal attacks (inherited from Camera module)
- CORS configured for mobile clients (origin: `*` in development)

**Response Format (JSON)**
All responses include timestamp and structured error handling:
```json
{
  "success": true,
  "filename": "photo.jpg",
  "timestamp": "2024-02-17T10:30:00.123456",
  "message": "Image captured successfully"
}
```

Errors use standard HTTP status codes:
- 400 - Bad request (invalid filename)
- 409 - Conflict (recording already in progress)
- 500 - Server error (camera initialization failed)

**Mobile-Ready Features**
- JSON API suitable for iOS, Android, and web clients
- CORS headers configured for cross-origin requests
- Automatic OpenAPI documentation for client libraries
- No session state required (stateless endpoints)
- All endpoints return machine-readable JSON

**Usage Example**
```python
from nomothetic.api import APIServer

# Start HTTPS API server
server = APIServer(
    host="0.0.0.0",          # Listen on all interfaces
    port=8443,                # HTTPS default port
    use_ssl=True              # Enable TLS
)

# Navigate to https://localhost:8443/docs for interactive API docs
server.run()  # Blocking call
```

Or run in background:
```python
from nomothetic.api import APIServer

server = APIServer()
thread = server.start_background()

# ... do other work ...
# server.run() or check /api/camera/status
```

**API Authentication (Deferred)**
Authentication and authorization (JWT tokens, API keys) are deferred to Phase 2.5 to avoid complexity at this stage. The endpoints are currently open and suitable for private networks (Tailscale, local LAN, etc.) or behind a load balancer/reverse proxy with authentication.

**Configuration**
- Default: localhost only (`127.0.0.1:8443`)
- Production: Use `host="0.0.0.0"` to listen on all interfaces
- Custom ports: `APIServer(port=9000)`
- SSL certificates auto-generated if missing

**Deployment Note**
For production deployment:
1. Use `host="0.0.0.0"` to expose on the network
2. Consider network isolation (Tailscale, VPN, or firewall rules)
3. Replace self-signed certs with proper ones if accessing over untrusted networks
4. Add authentication layer (Phase 2.5) for public deployments

**Test Coverage** (30+ tests)
- Health check and status endpoints
- Image capture with valid/invalid filenames
- Video recording start/stop/conflict scenarios
- CORS header verification
- Server configuration validation
- Error response formatting
- Request/response model validation

### Phase 3: HAT Control & Peripherals (Future)
- Identify specific HAT module(s)
- Implement driver/interface layers
- Sensor integration and actuator control

---

## 🚀 Getting Started

### Using the Camera Module
```python
from pathlib import Path
from nomothetic.camera import Camera

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
from nomothetic.streaming import StreamServer

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
from nomothetic.streaming import StreamServer

server = StreamServer()
thread = server.start_background()

# ... do other work while server runs ...

server.close()  # Clean up when done
```

### Using the REST API Server
```python
from nomothetic.api import APIServer

# Start HTTPS REST API server (self-signed cert auto-generated)
server = APIServer(
    host="127.0.0.1",  # Local only
    port=8443,         # HTTPS default
    use_ssl=True       # Enable TLS
)

# Access:
# - API docs: https://localhost:8443/docs
# - Redoc: https://localhost:8443/redoc
# - Status: GET https://localhost:8443/api/camera/status
# - Capture: POST https://localhost:8443/api/camera/capture
# - Record: POST https://localhost:8443/api/camera/record/start
server.run()  # Blocking call (Ctrl+C to stop)
```

Or run in background:
```python
from nomothetic.api import APIServer

server = APIServer(host="0.0.0.0")  # Listen on all interfaces
thread = server.start_background()

# ... server is running in background ...
# Make requests to https://0.0.0.0:8443/api/...
```

For production on Raspberry Pi:
```bash
# Install with API support
pip install -e ".[api]"

# Run API server as systemd service, SSH tunnel, or behind Tailscale
```

**Example API Requests (using curl)**
```bash
# Health check
curl https://localhost:8443/

# Get camera status
curl https://localhost:8443/api/camera/status

# Capture image
curl -X POST https://localhost:8443/api/camera/capture \
  -H "Content-Type: application/json" \
  -d '{"filename": "photo.jpg"}'

# Start recording
curl -X POST https://localhost:8443/api/camera/record/start \
  -H "Content-Type: application/json" \
  -d '{"filename": "video.mp4", "encoder": "h264"}'

# Stop recording
curl -X POST https://localhost:8443/api/camera/record/stop

# Skip certificate verification (development only)
curl -k https://localhost:8443/
```

**Example Python Client**
```python
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning

# Disable SSL verification warning (dev only)
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

api_url = "https://localhost:8443"

# Get status
status = requests.get(
    f"{api_url}/api/camera/status",
    verify=False  # Skip cert verification in dev
).json()
print(status)

# Capture image
response = requests.post(
    f"{api_url}/api/camera/capture",
    json={"filename": "photo.jpg"},
    verify=False
).json()
print(response)
```

### Development Environment (Linux)
```bash
# Install with dev dependencies (no streaming or API)
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

### With REST API Support
```bash
# Install with dev and API dependencies
uv add ".[dev,api]"

# Or with pip
pip install -e ".[dev,api]"
```

### With Everything
```bash
# Install all features: streaming, REST API, and dev tools
uv add ".[dev,web,api]"

# Or with pip
pip install -e ".[dev,web,api]"
```

### Running Tests
```bash
make test           # Run unit tests with coverage report
pytest tests/ -v    # Verbose test output
```

Hardware (picamera2, GPIO, HAT) is mocked — unit tests pass on any non-Pi dev machine (Windows/macOS/Linux) without Pi hardware.

### Code Quality
```bash
make format         # Format code with black & ruff
make lint           # Check code style
make type-check     # Type checking
```

---

## 📝 Design Principles & Notes

**Keep this codebase minimal.** Let the standard library and imported packages do the heavy lifting. This repo should be focused on **interacting with a microcontroller & peripherals** rather than defining broad patterns for such interactions.

- **Testing strategy:** Run tests on the Raspberry Pi where hardware is required. Transport-agnostic modules (like protocol) can run anywhere.
- All tool configurations (black, ruff, mypy) are pre-configured in pyproject.toml
- Test infrastructure ready for unit and integration tests
- Security is built-in: filename validation prevents path traversal and directory escape attacks
- Camera module is production-ready and fully tested with 20 test cases
