# GitHub Copilot Instructions — nomon

## Project Summary

`nomon` is a Python package targeting a small fleet of **Raspberry Pi microcontrollers** with HAT (Hardware Attached on Top) modules. Each Pi runs a self-contained HTTPS REST API (`nomon.api`) that exposes hardware control to a user mobile application and a centralized device management server.

The package is developed on Windows/macOS but deployed on **Raspberry Pi OS (Linux)**. Many hardware dependencies (`picamera2`, `spidev`, `pigpio`) are Linux-only and must be handled with conditional imports and graceful degradation so the package remains importable and testable on non-Pi systems.

---

## Architecture Overview

```
Mobile App  ────►  nomon REST API (HTTPS :8443)  ────►  Camera / HAT Hardware
                        │
              Tailscale VPN (admin access)
                        │
Mgmt Server  ◄───  MQTT telemetry (planned)
             ◄───  OTA update manifest (planned)
```

### Components

| Module | Class | Purpose |
|---|---|---|
| `nomon.camera` | `Camera` | picamera2 wrapper — still capture, video recording, MJPEG frames |
| `nomon.streaming` | `StreamServer` | Flask HTTP MJPEG stream server (local LAN viewing) |
| `nomon.api` | `APIServer` | FastAPI HTTPS REST server — primary remote control interface |

### Optional Dependency Groups (`pyproject.toml`)

- `[web]` — Flask for `StreamServer`
- `[api]` — FastAPI, uvicorn, cryptography, python-multipart, python-dotenv for `APIServer`
- `[dev]` — pytest, black, ruff, mypy for development

---

## Hardware Context

- **Camera**: OV5647 (Pi Camera v1.3) via FPC ribbon cable
  - Max still: 2592×1944 @ 15.63 fps
  - Default video: 1280×720 @ 30 fps
  - Encoders: H264 (default, 5 Mbps), MJPEG
- **HAT modules**: Not yet specified — to be determined in Phase 3
- **GPIO**: gpiozero (high-level) + pigpio (low-level daemon) + smbus2 (I2C) + pyserial (UART) + spidev (SPI, Linux-only)
- **Networking**: Tailscale VPN for admin access; self-signed TLS certs for HTTPS

---

## Coding Conventions

### Style
- **Formatter**: `black` (line length 100)
- **Linter**: `ruff` (pycodestyle, Pyflakes, isort, flake8-comprehensions, bugbear, pyupgrade)
- **Type checker**: `mypy` (strict return types, no bare `ignore_missing_imports` workarounds in new code)
- All public functions and classes must have **NumPy-style docstrings**
- All functions and methods must have **full type hints** including return types
- Use `raise ... from e` for exception chaining — never bare `raise ... from None` unless intentional

### Module Structure
- One class per module file is the norm
- Platform-conditional imports use `try/except ImportError` at module level, setting unavailable symbols to `None`
- Check for `None` at runtime, not at import time:
  ```python
  try:
      from picamera2 import Picamera2
  except ImportError:
      Picamera2 = None  # type: ignore

  class Camera:
      def __init__(self):
          if Picamera2 is None:
              raise RuntimeError("picamera2 not available — requires Raspberry Pi")
  ```

### File I/O and Security
- **Never** accept path-like filenames from external input — validate filenames to plain names only (no `/`, `\`, `..`, `.` prefix, no absolute paths)
- Files are always written inside a configured `directory` — never outside it
- Camera TLS certs live in `.certs/` (gitignored)
- Environment variables loaded via `python-dotenv`; never hardcode secrets

### API Design
- REST endpoints are stateless — no server-side sessions
- All responses include a UTC `timestamp` ISO 8601 field
- Use Pydantic models (`BaseModel`) for all request and response bodies
- HTTP status codes: `400` bad input, `409` conflict state, `500` server/hardware error
- CORS is `allow_origins=["*"]` in development; restrict in production

### Testing
- Tests live in `tests/` and follow `test_*.py` naming
- Hardware (picamera2, Flask, FastAPI) is mocked — tests must pass on non-Pi, non-Linux systems
- Use `pytest` markers for any tests that require hardware
- Target: all tests pass with `make test` on Windows/macOS
- Current test count: 63 (20 camera + 14 streaming + 26 API + 3 integration)

---

## Development Commands

```bash
make install-dev   # pip install -e ".[dev,web,api]"
make test          # pytest with coverage
make lint          # ruff check
make format        # black .
make type-check    # mypy src/
make clean         # remove __pycache__, .egg-info, dist
```

---

## What Not to Do

- Do **not** add synchronous blocking calls inside FastAPI async route handlers — use `asyncio.to_thread` or background threads
- Do **not** import `spidev` unconditionally — it fails on non-Linux
- Do **not** catch bare `Exception` without re-raising or logging
- Do **not** add new top-level dependencies to `pyproject.toml` without discussion — keep the core dependency list minimal
- Do **not** use `print()` for logging in library code — use Python `logging` module (future standard)
- Do **not** commit `.certs/`, `.env`, or any generated key material

---

## Planned Next Phases

- **Phase 2.5** (optional): JWT auth, API key management, rate limiting, audit logging
- **Phase 3**: MQTT telemetry publishing
- **Phase 4**: OTA update mechanism + version manifest endpoint
- **Phase 5**: HAT module driver(s) — identify hardware, implement control interface, add REST endpoints
- **Mobile App**: Separate repository, consumes nomon REST API

See [docs/roadmap.md](../docs/roadmap.md) for full detail.
