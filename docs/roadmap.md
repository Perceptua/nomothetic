# nomon — Development Roadmap

## Status Summary

| Phase | Name | Status |
|-------|------|--------|
| 1 | Camera Module | ✅ Complete |
| 1.5 | MJPEG Stream Server | ✅ Complete |
| 2 | HTTPS REST API | ✅ Complete |
| 2.5 | Auth & Rate Limiting | 🔲 Optional / Deferred |
| 3 | MQTT Telemetry | ✅ Complete |
| 4 | OTA Update Mechanism | 🔲 Planned |
| 5 | HAT Module Driver | 🔲 Planned |

---

## Completed Phases

### Phase 1 — Camera Module (`nomon.camera`)

**Deliverables:**
- `Camera` class wrapping `picamera2` for OV5647 sensor
- Still image capture: `capture_image(filename)`
- Video recording: `start_recording(filename)` / `stop_recording()`
- JPEG frame generator: `get_jpeg_frame_generator()`
- Encoder selection: H264 (default, 5 Mbps) or MJPEG
- Filename-only security validation with path traversal protection
- 20 passing tests

**Hardware specs confirmed:**
- Default video: 1280×720 @ 30 fps
- Max still: 2592×1944 @ 15.63 fps

---

### Phase 1.5 — MJPEG Stream Server (`nomon.streaming`)

**Deliverables:**
- `StreamServer` class using Flask
- HTML viewer at `GET /` with dark-themed responsive layout
- MJPEG stream at `GET /stream` (multipart/x-mixed-replace)
- Blocking (`start()`) and background thread (`start_background()`) modes
- Optional dependency: Flask in `[web]` group
- 14 passing tests

---

### Phase 2 — HTTPS REST API (`nomon.api`)

**Deliverables:**
- `APIServer` class using FastAPI + uvicorn
- HTTPS with auto-generated self-signed certificates in `.certs/`
- 5 camera control endpoints (see architecture.md)
- Pydantic request/response models with UTC timestamps
- CORS middleware for mobile clients
- OpenAPI docs at `/docs` and `/redoc`
- Optional dependency: FastAPI, uvicorn, cryptography, python-multipart, python-dotenv in `[api]` group
- 26 passing tests

**Test totals: 63 passing (20 camera + 14 streaming + 26 API + 3 integration)**

---

### Phase 3 — MQTT Telemetry (`nomon.telemetry`)

**Deliverables:**
- `TelemetryPublisher` class using `paho-mqtt` 2.x
- Background daemon thread (non-blocking, REST API unaffected)
- Structured JSON telemetry payload (device ID, camera status, nomon version, UTC timestamp)
- Configurable broker host/port/topic/interval via `.env` (`NOMON_MQTT_*`)
- Device ID auto-detection: env var → `/proc/cpuinfo` Pi serial → hostname
- Reconnect/retry with exponential back-off (1 s → 60 s cap)
- Optional dependency: `paho-mqtt` in `[telemetry]` group
- 23 passing tests

**Test totals: 86 passing (20 camera + 14 streaming + 26 API + 3 integration + 23 telemetry)**

---

## Upcoming Phases

### Phase 2.5 — Authentication & Rate Limiting (Optional)

Adds security layers on top of the existing API. Can be deferred since Tailscale VPN currently provides network-layer access control.

**Candidate deliverables:**
- [ ] JWT token issuance and validation middleware
- [ ] API key management (create/revoke/list via admin endpoint)
- [ ] Per-client rate limiting
- [ ] Request audit logging (structured JSON log file)
- [ ] `GET /api/admin/keys` endpoint (protected)

**Implementation approach:**
- Middleware-first: avoid coupling auth logic into route handlers
- Consider `fastapi-users` or hand-rolled JWT with `python-jose`/`authlib`
- Rate limiting via `slowapi` (wraps `limits`)
- Log to file; Phase 3 MQTT can forward logs to management server

---

### Phase 4 — OTA Update Mechanism

**Purpose:** Allow fleet devices to pull and apply updates from the management server without manual SSH access.

**Candidate deliverables:**
- [ ] `nomon.updater` module
- [ ] `GET /api/system/version` endpoint (current version + git hash)
- [ ] Version manifest endpoint on management server
- [ ] Polling loop to check for updates
- [ ] Update procedure: `git pull` + graceful restart via systemd
- [ ] Rollback mechanism on failed start

**Design constraints:**
- Must not interrupt active camera sessions mid-recording
- systemd service required for restart capability
- SHA-256 checksum verification of update packages

---

### Phase 5 — HAT Module Driver

**Prerequisites:** Identify the specific HAT hardware module(s) to be used.

**Candidate deliverables:**
- [ ] `nomon.hat` (or named after hardware) module with conditional imports
- [ ] Driver class following the `Camera` pattern (raises `RuntimeError` if hardware unavailable)
- [ ] REST endpoints under `/api/hat/...` in `nomon.api`
- [ ] Tests with mocked hardware
- [ ] Hardware discovery guide in `docs/`

**Design constraints:**
- SPI access via `spidev` (Linux-only conditional import)
- I2C access via `smbus2`
- GPIO via `gpiozero` (high-level) + `pigpio` (low-level daemon)
- Must be testable on Windows/macOS with mocks

---

## Mobile App

Developed in a separate repository. Consumes the `nomon` REST API.

**Expected interface:**
- HTTPS requests to `https://<pi-tailscale-ip>:8443`
- Self-signed cert acceptance (trust on first use or pinned cert)
- Endpoints: status, capture, record start/stop
- Future: stream preview, telemetry dashboard, HAT control

---

## Management Server

Developed in a separate repository.

**Expected interface:**
- MQTT broker (receives telemetry from fleet)
- Version manifest endpoint (serves release metadata for OTA)
- Object storage (S3-compatible) for release artifacts
- Admin dashboard for fleet monitoring
