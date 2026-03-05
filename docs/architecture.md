# nomon — Architecture

## System Overview

nomon runs on a small fleet of Raspberry Pi microcontrollers, each operating independently as a self-contained node. A mobile app and centralized management server interact with each Pi via its REST API.

```
┌─────────────────────────────────────────────────────────────┐
│  Client Layer                                               │
│                                                             │
│   Mobile App          Mgmt Server           Admin (SSH)     │
│       │                   │                      │          │
│       │ HTTPS :8443        │ MQTT telemetry       │ Tailscale│
└───────┼───────────────────┼──────────────────────┼──────────┘
        │                   │                      │
┌───────▼───────────────────▼──────────────────────▼──────────┐
│  Raspberry Pi Node                                           │
│                                                             │
│   nomon.api (FastAPI/uvicorn)   StreamServer (Flask/MJPEG) │
│         │                               │                   │
│   nomon.camera (picamera2)──────────────┘                   │
│         │                                                   │
│   nomon.telemetry (paho-mqtt) ──────────► MQTT broker       │
│         │                                                   │
│   nomon.api ─── IPC ───► nomon-hat (Rust daemon, Phase 5)   │
│                             │                                │
│                       GPIO / I2C / SPI / UART Hardware       │
└─────────────────────────────────────────────────────────────┘
```

---

## Module Responsibilities

### `nomon.camera` — `Camera`

The lowest-level hardware abstraction. Wraps `picamera2` directly.

**Responsibilities:**
- Initialize and configure the OV5647 sensor
- Still image capture → JPEG files on disk
- Video recording → H264/MJPEG files on disk
- Provide a JPEG frame generator for streaming consumers
- Enforce filename safety (no path traversal)

**Key design decisions:**
- Conditional `picamera2` import — module is importable on non-Pi systems
- `directory` parameter controls where all files are written; never allows escape
- Single encoder instance; switching encoder requires reinitialization
- `get_jpeg_frame_generator()` yields raw JPEG bytes — both `StreamServer` and future direct callers use this

**Does NOT:**
- Serve HTTP
- Do network I/O
- Have awareness of the REST API

---

### `nomon.streaming` — `StreamServer`

A lightweight local LAN viewer. Not used by the mobile app.

**Responsibilities:**
- Create a `Camera` instance internally
- Serve an HTML viewer page at `/`
- Serve an MJPEG stream at `/stream` (multipart/x-mixed-replace)
- Run in foreground (`start()`) or background thread (`start_background()`)

**Key design decisions:**
- Flask chosen for minimal overhead — two endpoints only (see ADR-003)
- HTTP (not HTTPS) — LAN-only, not exposed to mobile clients
- Thread-safe frame sharing via `_frame_lock`
- Default binding: `localhost` — must be explicitly changed for LAN access

**Port:** 8000 (default, configurable)

---

### `nomon.api` — `APIServer` / `create_app()`

The primary remote control interface. Mobile app and management server talk to this.

**Responsibilities:**
- Expose camera operations as a JSON REST API
- Terminate HTTPS/TLS connections using self-signed certs
- Auto-generate self-signed certs on first run (stored in `.certs/`)
- Run in foreground (`run()`) or background thread (`start_background()`)
- Validate all incoming request data via Pydantic models

**Key design decisions:**
- FastAPI chosen for automatic OpenAPI docs and Pydantic integration (see ADR-002)
- Self-signed certs chosen for zero-configuration private network deployment (see ADR-001)
- CORS `allow_origins=["*"]` in development — restrict for production
- Global `_camera` instance managed by FastAPI lifespan context manager
- All responses include a UTC `timestamp` ISO 8601 field

**Port:** 8443 (default, configurable)

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check |
| `GET` | `/api/camera/status` | Camera state (resolution, fps, encoder, recording) |
| `POST` | `/api/camera/capture` | Still image capture |
| `POST` | `/api/camera/record/start` | Start video recording |
| `POST` | `/api/camera/record/stop` | Stop video recording |
| `GET` | `/docs` | Interactive Swagger UI |
| `GET` | `/redoc` | ReDoc API docs |

**HTTP Status Codes:**

| Code | Meaning |
|------|---------|
| `200` | Success |
| `400` | Bad request (invalid filename, bad parameters) |
| `409` | Conflict (recording already in/not in progress) |
| `500` | Server/hardware error |

---

### `nomon.telemetry` — `TelemetryPublisher`
A background telemetry publisher. Sends structured JSON to an MQTT broker.

**Responsibilities:**
- Discover device identity (env var → Pi serial → hostname)
- Build a JSON telemetry payload (device ID, timestamp, nomon version, camera status)
- Publish periodically over MQTT in a daemon background thread
- Handle broker unavailability with exponential back-off reconnect
- Expose a one-shot `publish_now()` for scripted or ad-hoc use

**Key design decisions:**
- Conditional `paho-mqtt` import — module is importable without paho-mqtt installed
- Fully standalone — no coupling to `APIServer` or `StreamServer` lifecycle
- `threading.Event` shutdown signal for clean daemon thread exit
- Back-off: 1 s → 2 s → 4 s → … capped at 60 s; resets on successful connect
- Camera is optional — payload `"camera"` field is `null` if no `Camera` provided
- All config via env vars (`NOMON_MQTT_*`) or constructor arguments

**Does NOT:**
- Receive MQTT messages (subscribe)
- Expose HTTP endpoints
- Block the REST API

**Port:** N/A — uses MQTT (default TCP 1883)

---

### `nomon.updater` — `UpdateManager`

Polls a remote version manifest and applies OTA updates.

**Responsibilities:**
- Fetch and parse a JSON version manifest via `urllib.request` (no extra deps)
- Compare manifest version against currently installed `nomon.__version__`
- Optionally auto-apply updates (`NOMON_UPDATE_AUTO_APPLY=true`)
- Apply via `git fetch + reset --hard`, SHA verification, pre-flight import check, `systemctl restart`
- Roll back (`git reset --hard <prev_hash>`) if pre-flight fails — never leaves broken state
- Run as a daemon background thread alongside the REST API

**Key design decisions:**
- Stdlib-only: `urllib.request`, `subprocess`, `hashlib`, `threading` — zero new dependencies
- Notify-only default; explicit opt-in for auto-apply
- Pre-flight check: runs `python -c "import nomon"` in a fresh subprocess before any restart
- Abort if camera is recording — will not interrupt active sessions

**Does NOT:**
- Require, or couple to, the management server (manifest URL is configurable)
- Handle post-restart rollback (pre-flight failure is caught before restart)

---

## Data Flow — Still Capture

```
Mobile App
  POST /api/camera/capture {"filename": "photo.jpg"}
        │
  APIServer (FastAPI route)
        │ validates filename
        │ calls Camera.capture_image("photo.jpg")
        │
  Camera
        │ starts picamera2 still config
        │ captures frame to disk at <directory>/photo.jpg
        │ returns
        │
  APIServer
        └─► 200 {"success": true, "filename": "photo.jpg", "timestamp": "..."}
```

---

## Data Flow — MJPEG Stream

```
Browser / LAN Client
  GET /stream (HTTP)
        │
  StreamServer (Flask)
        │ opens multipart/x-mixed-replace response
        │
  Camera.get_jpeg_frame_generator()
        │ yields JPEG bytes from picamera2
        │
  StreamServer
        └─► streams boundary-wrapped JPEG frames continuously
```

---

## Security Model

| Concern | Approach |
|---------|----------|
| Transport encryption | TLS 1.2+ via uvicorn; self-signed cert auto-generated |
| Authentication (current) | None — relies on Tailscale VPN for network-layer access control |
| Authentication (planned) | JWT tokens or API keys (Phase 2.5) |
| Path traversal | Filename-only validation in `Camera`; rejects `/`, `\`, `..`, `.` prefix, absolute paths |
| CORS | `allow_origins=["*"]` in dev; tighten for production |
| Secrets | `python-dotenv` for envvars; `.env` and `.certs/` are gitignored |

---

## Dependency Map

```
nomon.api
  ├── nomon.camera
  ├── fastapi
  ├── uvicorn
  ├── pydantic
  ├── cryptography
  └── python-dotenv

nomon.streaming
  ├── nomon.camera
  └── flask

nomon.camera
  ├── picamera2  (Linux only — conditional import)
  └── (no other runtime deps)

nomon.telemetry
  ├── nomon (for __version__)
  ├── paho-mqtt  (optional — conditional import)
  └── (standard library: threading, json, socket, os)

nomon.updater
  ├── nomon (for __version__)
  └── (standard library: urllib.request, subprocess, hashlib, threading, os)
```

---

## Planned Additions

### Phase 4 — OTA Updates ✅

`nomon.updater.UpdateManager` polls a version manifest endpoint and orchestrates
`git fetch + reset --hard` + restart via a systemd service.  Pre-flight import
checks guard against broken updates; automatic git rollback runs if the check fails.

### Phase 5 — HAT Module Driver (Rust, Separate Repo)

A standalone Rust daemon in a new `nomon-hat` repository (see ADR-006). Runs
as `nomon-hat.service` and communicates with `nomon.api` via local IPC (Unix
domain socket at `/run/nomon-hat.sock` or localhost HTTP fallback). Python was
evaluated and rejected for HAT drivers due to GIL-induced latency in
timing-critical GPIO/SPI operations.

`nomon.api` HAT endpoints (`/api/hat/...`) proxy requests to the Rust daemon.
If the daemon is not running, HAT endpoints return `503 Service Unavailable`.

The interface contract (JSON schema) will be documented here when HAT hardware
is identified.

### Phase 6 — AWS IoT Jobs Migration (Planned)

Replaces the `nomon.updater` polling-based OTA strategy with push-based
updates via AWS IoT Jobs (see ADR-007). A single job document coordinates
versions for both the Python `nomon` package and the Rust `nomon-hat` binary.
`nomon.telemetry` may consolidate its MQTT connection with the IoT Jobs
subscription to use a single AWS IoT Core broker.

---

## Repository Strategy

All Python modules remain in this single repository. The `UpdateManager`
(Phase 4) relies on a single-repo atomic update (`git fetch + reset --hard`);
splitting Python modules would break atomicity and require dual-manifest OTA.

The Rust HAT daemon (`nomon-hat`) lives in a separate repository because it
produces a different build artifact (compiled binary), uses a different update
mechanism (artifact download, not git), runs as a separate systemd service,
and has an independent release cadence. See ADR-006 for the full rationale.

```
nomon/              ← Python monorepo (this repo)
  nomon.camera
  nomon.streaming
  nomon.api
  nomon.telemetry
  nomon.updater

nomon-hat/          ← Rust repo (Phase 5, separate)
  Cargo.toml
  src/main.rs
  systemd/nomon-hat.service
```
