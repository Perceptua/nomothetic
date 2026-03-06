# GitHub Copilot Instructions — nomon

## Project Summary

`nomon` is a Python package targeting a small fleet of **Raspberry Pi microcontrollers** with HAT (Hardware Attached on Top) modules. Each Pi runs a self-contained HTTPS REST API (`nomon.api`) that exposes hardware control to a user mobile application and a centralized device management server.

The package is developed on Windows/macOS but deployed on **Raspberry Pi OS (Linux)**. Many hardware dependencies (`picamera2`, `spidev`, `pigpio`) are Linux-only and must be handled with conditional imports and graceful degradation so the package remains importable and testable on non-Pi systems.

---

## Architecture Overview

```
Mobile App  ────►  nomon REST API (HTTPS :8443)  ────►  Camera / HAT Hardware
                        │                                      ▲
              Tailscale VPN (admin access)        NDJSON / Unix socket
                        │                                      │
Mgmt Server  ◄───  MQTT telemetry               nomon-hat (Rust daemon)
             ◄───  OTA update dispatch (AWS IoT Jobs, planned)
```

### Components

| Module | Class | Purpose |
|---|---|---|
| `nomon.camera` | `Camera` | picamera2 wrapper — still capture, video recording, MJPEG frames |
| `nomon.streaming` | `StreamServer` | Flask HTTP MJPEG stream server (local LAN viewing) |
| `nomon.api` | `APIServer` | FastAPI HTTPS REST server — primary remote control interface |
| `nomon.telemetry` | `TelemetryPublisher` | paho-mqtt background telemetry publisher |
| `nomon.updater` | `UpdateManager` | OTA update manager — manifest polling, git-based apply, rollback |
| `nomon.hat` | `HatClient` | IPC client for the `nomon-hat` Rust daemon (Phase 5) |

### Optional Dependency Groups (`pyproject.toml`)

- `[web]` — Flask for `StreamServer`
- `[api]` — FastAPI, uvicorn, cryptography, python-multipart, python-dotenv for `APIServer`
- `[telemetry]` — paho-mqtt for `TelemetryPublisher`
- `[dev]` — pytest, black, ruff, mypy for development

---

## Hardware Context

- **Device**: Raspberry Pi Zero 2 W running Debian GNU/Linux 13 (trixie)
- **Camera**: OV5647 (Pi Camera v1.3) via FPC ribbon cable
  - Max still: 2592×1944 @ 15.63 fps
  - Default video: 1280×720 @ 30 fps
  - Encoders: H264 (default, 5 Mbps), MJPEG
  - I2C: muxed buses 10/11, address 0x36 (kernel-managed, do not touch)
- **HAT**: SunFounder Robot HAT V4 — I2C bus 1, address `0x14`
  - PWM controller (servo): REG_CHN=0x20, REG_PSC=0x40, REG_ARR=0x44; CLOCK=72 MHz
  - Servo: 50 Hz, PERIOD=4095, pulse width 500–2500 µs
  - Battery ADC: channel A4, scaling `battery_v = adc_voltage × 3`
  - SPI nodes exist (`/dev/spidev0.0`, `/dev/spidev0.1`) but HAT is primarily I2C
- **HAT code location**: **All hardware control lives in the `nomon-hat` Rust daemon** (separate repo, Phase 5). The Python `nomon` package connects to it via `nomon.hat.HatClient` over a Unix domain socket. Never add I2C register writes, ADC formulae, or GPIO BCM numbers to the Python codebase.
- **IPC**: Unix domain socket at `/run/nomon-hat/nomon-hat.sock`, NDJSON framing. Schema: `docs/hat_ipc_schema.md`.
- **GPIO**: accessed only from Rust (`rppal`) via `nomon-hat`. Python never touches GPIO directly.

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
- `nomon.hat` tests use a mock Unix socket server fixture — no Raspberry Pi required
- Use `pytest` markers for any tests that require hardware
- Target: all tests pass with `make test` on Windows/macOS
- Current test count: 146 (20 camera + 14 streaming + 38 API + 3 integration + 23 telemetry + 48 updater)

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
- Do **not** add I2C register writes, ADC scaling, PWM prescaler calculations, or GPIO BCM pin numbers to Python code — all hardware logic belongs in the `nomon-hat` Rust daemon
- Do **not** call `nomon.hat.HatClient` methods directly from async route handlers without `asyncio.to_thread` — the client uses blocking socket I/O

---

## HAT Control — Where Code Lives

| What | Where |
|------|-------|
| I2C register addresses, ADC formulae, PWM prescalers | `nomon-hat` Rust repo |
| GPIO BCM pin numbers, servo pulse math | `nomon-hat` Rust repo |
| IPC socket framing / NDJSON parse | `nomon-hat` Rust + `nomon.hat.HatClient` (Python) |
| Typed Python methods (`get_battery_voltage`, `set_servo_angle`) | `src/nomon/hat.py` |
| REST endpoints proxying HAT operations | `src/nomon/api.py` (`/api/hat/...`) |
| Hardware tests (mock socket, no Pi required) | `tests/test_hat.py` |

See `docs/hat_ipc_schema.md`, `docs/nomon_hat_crate.md`, and
`docs/hat_python_client.md` for full specifications.

---

## Planned Next Phases

- **Phase 2.5** (optional): JWT auth, API key management, rate limiting, audit logging
- **Phase 5**: Rust HAT/sensor drivers in separate `nomon-hat` repo (see ADR-006 and `docs/nomon_hat_crate.md`); Python client in `nomon.hat` (see `docs/hat_python_client.md`); IPC schema in `docs/hat_ipc_schema.md`
- **Phase 6** (planned): AWS IoT Jobs migration — push-based OTA replacing manifest polling (see ADR-007)
- **Mobile App**: Separate repository, consumes nomon REST API

See [docs/roadmap.md](../docs/roadmap.md) for full detail.
