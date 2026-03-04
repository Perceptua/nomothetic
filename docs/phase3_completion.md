# Phase 3 Completion Summary: MQTT Telemetry

## Overview

**Phase 3 is complete.** Each nomon device can now publish structured JSON telemetry
to a centralized MQTT broker. The publisher runs as a non-blocking daemon thread
alongside the REST API.

---

## What Was Built

### Technology Stack

- **paho-mqtt >= 2.0** — Eclipse Paho Python MQTT client (2.x API with `CallbackAPIVersion`)
- **Python standard library** — `threading`, `json`, `socket`, `os` — no other new deps

### `nomon.telemetry` — `TelemetryPublisher`

| Feature | Description |
|---------|-------------|
| Background thread | Daemon thread; does not block the REST API |
| Reconnect/retry | Exponential back-off: 1 s → 2 s → 4 s → … capped at 60 s |
| Graceful shutdown | `threading.Event` stop signal; clean thread join |
| Device ID detection | `NOMON_DEVICE_ID` env → `/proc/cpuinfo` Pi serial → `hostname` |
| Optional camera | Camera status included in payload when a `Camera` instance is provided |
| `.env` config | All parameters configurable via environment variables |
| Conditional import | Module importable without paho-mqtt; raises at instantiation only |

### Telemetry Payload

```json
{
  "device_id": "pi-deadbeef",
  "timestamp": "2026-03-03T11:23:17.638000+00:00",
  "nomon_version": "0.1.0",
  "camera": {
    "ready": true,
    "recording": false,
    "resolution": "1280x720",
    "fps": 30,
    "encoder": "h264"
  }
}
```

`"camera"` is `null` when no `Camera` instance is provided.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NOMON_MQTT_BROKER` | *(required)* | Broker hostname or IP |
| `NOMON_MQTT_PORT` | `1883` | Broker TCP port |
| `NOMON_MQTT_TOPIC` | `nomon/telemetry` | Publish topic |
| `NOMON_MQTT_INTERVAL` | `30.0` | Seconds between publishes |
| `NOMON_DEVICE_ID` | *(auto)* | Device identifier (overrides auto-detection) |

---

## Implementation Details

### Source (`src/nomon/telemetry.py`)

- ~310 lines of production code
- Full NumPy-style docstrings and type hints
- `TelemetryPublisher` class with public API:
  - `__init__(broker, port, topic, device_id, camera, interval, qos)`
  - `from_env(camera) -> TelemetryPublisher` — classmethod for `.env` config
  - `start_background() -> threading.Thread`
  - `stop() -> None`
  - `publish_now() -> bool`
  - `build_payload() -> dict` — public for testability
  - `get_device_id() -> str` — static method

### Test Coverage (`tests/test_telemetry.py`)

**23 tests** covering:
- Constructor defaults and custom parameters
- `from_env()` reads all MQTT env vars; raises on missing broker
- `get_device_id()` — env var, `/proc/cpuinfo` parsing, hostname fallback
- `build_payload()` — without camera, with mock camera, recording state, UTC timestamp, camera error graceful handling
- `start_background()` starts a daemon thread; `stop()` signals shutdown
- `publish_now()` — success, connection failure, skip-connect-when-connected
- Exponential back-off logic (first delay = `_BACKOFF_BASE`; cap at `_BACKOFF_CAP`)
- `ImportError` raised when paho-mqtt not installed
- Package-level `nomon.TelemetryPublisher` export

**Test totals: 86 passing (20 camera + 14 streaming + 26 API + 3 integration + 23 telemetry)**

### Code Quality

- ✅ **Black** — Code formatting (line length 100)
- ✅ **Ruff** — Linting (all checks pass for new code)
- ✅ **mypy** — Full static type checking (no issues)
- ✅ **Docstrings** — All public functions documented
- ✅ **Exception chaining** — `raise ... from` used throughout

---

## Usage

### Basic Setup

```python
from nomon.telemetry import TelemetryPublisher

pub = TelemetryPublisher(broker="192.168.1.100")
thread = pub.start_background()

# ... application runs ...

pub.stop()
thread.join()
```

### With Camera Status

```python
from nomon.camera import Camera
from nomon.telemetry import TelemetryPublisher

camera = Camera()
pub = TelemetryPublisher(broker="192.168.1.100", camera=camera)
thread = pub.start_background()
```

### From `.env`

```dotenv
# .env
NOMON_MQTT_BROKER=192.168.1.100
NOMON_MQTT_PORT=1883
NOMON_MQTT_TOPIC=fleet/telemetry
NOMON_MQTT_INTERVAL=30.0
NOMON_DEVICE_ID=pi-lab-01
```

```python
from dotenv import load_dotenv
from nomon.telemetry import TelemetryPublisher

load_dotenv()
pub = TelemetryPublisher.from_env()
thread = pub.start_background()
```

### One-Shot Publish

```python
pub = TelemetryPublisher(broker="192.168.1.100")
success = pub.publish_now()
```

### Installation

```bash
# Install with telemetry support
pip install -e ".[telemetry]"

# All features
pip install -e ".[dev,web,api,telemetry]"
```

---

## Architecture Decisions

### Why paho-mqtt?

See [ADR-005](adr/005-paho-mqtt-for-telemetry.md) for the full decision record.
In brief: it is the de facto standard Python MQTT client, is well-documented,
actively maintained, supports MQTTv5, and has no transitive dependencies.

### Why a daemon thread (not asyncio)?

The REST API and MQTT publisher run concurrently. A daemon thread is sufficient
here: it does not share mutable state with the REST API, and blocking I/O
(MQTT `connect`, `publish`) is acceptable on a background thread. Using asyncio
would require migrating the entire application to async or bridging event loops,
adding complexity for no practical gain.

### Why exponential back-off?

If the MQTT broker is unavailable at startup or goes down during operation,
tight reconnect loops would saturate CPU and network logs. Capped exponential
back-off (max 60 s) reduces noise while still recovering promptly after
brief outages.

---

## What's Next

### Phase 4 — OTA Update Mechanism

- `nomon.updater` module
- `GET /api/system/version` endpoint
- Version manifest polling + `git pull` + systemd restart
- SHA-256 checksum verification
