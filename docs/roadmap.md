# nomon — Development Roadmap

## Status Summary

| Phase | Name | Status |
|-------|------|--------|
| 1 | Camera Module | ✅ Complete |
| 1.5 | MJPEG Stream Server | ✅ Complete |
| 2 | HTTPS REST API | ✅ Complete |
| 2.5 | Auth & Rate Limiting | 🔲 Optional / Deferred |
| 3 | MQTT Telemetry | ✅ Complete |
| 4 | OTA Update Mechanism | ✅ Complete |
| 5 | HAT Module Driver (Rust) | 🔲 Planned |
| 6 | AWS IoT Jobs Migration | 🔲 Planned |

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

### Phase 4 — OTA Update Mechanism (`nomon.updater`)

**Deliverables:**
- `UpdateManager` class in `nomon.updater`
- Polls a remote JSON version manifest (stdlib `urllib.request` — no new deps)
- Notify-only by default; `NOMON_UPDATE_AUTO_APPLY=true` for automatic apply
- Update procedure: `git fetch + reset --hard` → SHA verification → pre-flight import check → `systemctl restart`
- Rollback on failure: `git reset --hard <prev_hash>` before raising, so no broken state is left
- Must not apply update while camera is recording
- Background daemon thread (same pattern as `TelemetryPublisher`)
- `from_env()` classmethod; all config via `NOMON_UPDATE_*` env vars
- Three new REST endpoints: `GET /api/system/version`, `GET /api/system/update/status`, `POST /api/system/update/apply`
- 60 new tests

**Test totals: 146 passing (20 camera + 14 streaming + 38 API + 3 integration + 23 telemetry + 48 updater)**

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

### Phase 5 — HAT Module Driver (Rust, Separate Repo)

**Prerequisites:** Identify the specific HAT hardware module(s) to be used.

**Language & repo:** Rust, in a new `nomon-hat` repository (see ADR-006).
Rust is chosen for deterministic latency in GPIO/SPI timing-critical
operations. The Python modules remain in this repo — they are I/O-bound
and gain nothing from a Rust conversion.

**Candidate deliverables:**
- [ ] `nomon-hat` Rust binary using `rppal` for GPIO/SPI/I2C access
- [ ] Runs as `nomon-hat.service` (separate systemd unit)
- [ ] Local IPC interface (Unix domain socket at `/run/nomon-hat.sock`, JSON protocol)
- [ ] REST endpoints under `/api/hat/...` in `nomon.api` that proxy to the Rust daemon
- [ ] OTA binary deploy script (artifact download + SHA-256 verify + atomic swap)
- [ ] Hardware discovery guide in `docs/`

**Design constraints:**
- Cross-compiled for `aarch64-unknown-linux-gnu` (CI uses `cross` or equivalent)
- `nomon.api` HAT endpoints return `503 Service Unavailable` if the Rust daemon is not running
- Interface contract (JSON schema) documented in `docs/architecture.md`
- Python tests mock the IPC socket — testable on Windows/macOS

---

### Phase 6 — AWS IoT Jobs Migration (Planned)

Replaces the current `nomon.updater` polling-based OTA strategy with
push-based updates via AWS IoT Jobs. See ADR-007.

**Candidate deliverables:**
- [ ] Refactor `nomon.updater` to subscribe to AWS IoT Jobs MQTT topic
- [ ] Artifact-based deployment (S3 download) instead of `git fetch + reset --hard`
- [ ] Multi-repo coordination: single job document specifies versions for both `nomon` (Python) and `nomon-hat` (Rust)
- [ ] X.509 certificate provisioning per device (replaces Tailscale-only trust for update channel)
- [ ] Consolidate MQTT connections: telemetry + job subscription on same AWS IoT Core broker
- [ ] Preserve existing REST endpoints (`/api/system/version`, `/api/system/update/status`, `/api/system/update/apply`)

**Dependency:** AWS IoT Device SDK for Python (~5 MB). Greengrass v2 is
explicitly **not** used due to JVM memory requirements on Pi Zero hardware.

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

**AWS IoT path (Phase 6):** If AWS IoT is adopted, the management server uses
AWS IoT Core as the MQTT broker and AWS IoT Jobs for fleet update dispatch.
See ADR-007 and [docs/phase5_planning.md](phase5_planning.md).
