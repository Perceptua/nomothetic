# nomon

Controls, telemetry, & updates for the `nomon` fleet.

This Python package provides peripheral control, HTTPS REST API, MQTT telemetry, and OTA updates for a fleet of Raspberry Pi devices.

---

## Modules

| Module | Class | Description |
|---|---|---|
| `nomon.camera` | `Camera` | picamera2 wrapper — still capture, video recording, MJPEG frames |
| `nomon.streaming` | `StreamServer` | Flask MJPEG stream server for local LAN viewing |
| `nomon.api` | `APIServer` | FastAPI HTTPS REST server — primary remote control interface |
| `nomon.telemetry` | `TelemetryPublisher` | paho-mqtt background telemetry publisher |
| `nomon.updater` | `UpdateManager` | OTA update manager — manifest polling, git-based apply, rollback |
| *(planned)* | *(planned)* | HAT IPC client for the future `nomon-hat` Rust daemon *(Phase 5; Python client not yet implemented, module not available in current release)* |

See [docs/architecture.md](docs/architecture.md) for a full system diagram and module responsibilities.

---

## Installation

nomon uses optional dependency groups — install only what you need:

```bash
# HTTPS REST API (most common)
pip install "nomon[api]"

# MJPEG stream server (local LAN)
pip install "nomon[web]"

# MQTT telemetry
pip install "nomon[telemetry]"

# All runtime extras
pip install "nomon[api,web,telemetry]"
```

> **Note:** Some hardware dependencies (e.g., `picamera2`, `spidev`) are Linux-only, and camera/SPI functionality is only supported on Raspberry Pi OS. The package remains importable on Windows/macOS for development and testing.

---

## Quick Start

### REST API

```python
from nomon.api import APIServer

server = APIServer(host="0.0.0.0", port=8443, use_ssl=True)
server.run()  # HTTPS on :8443; self-signed cert auto-generated in .certs/
```

See [examples/api_server.py](examples/api_server.py) for a fuller example and [docs/architecture.md](docs/architecture.md) for the full endpoint reference.

### MJPEG Stream (local LAN)

```python
from nomon.streaming import StreamServer

stream = StreamServer(host="0.0.0.0", port=8000)
stream.start()  # http://<pi-ip>:8000/stream
```

### MQTT Telemetry

```python
from nomon.telemetry import TelemetryPublisher

pub = TelemetryPublisher(broker="mqtt.example.com", topic="nomon/telemetry")
pub.start_background()  # daemon thread; publishes a JSON payload every 30 s by default
```

Configured via `NOMON_MQTT_*` environment variables. See [docs/phase3_completion.md](docs/phase3_completion.md) for the full variable reference.

### OTA Updates

```python
from nomon.updater import UpdateManager

mgr = UpdateManager.from_env()  # configure via NOMON_UPDATE_* env vars
mgr.start_background()  # daemon thread; polls manifest and optionally auto-applies updates
```

See [docs/phase4_completion.md](docs/phase4_completion.md) for the manifest format and environment variable reference.

---

## Development

```bash
make install-dev   # pip install -e ".[dev,web,api]"
make test          # pytest with coverage
make lint          # ruff check
make format        # black .
make type-check    # mypy src/
```

Tests pass on Windows/macOS — hardware is fully mocked. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## Roadmap

See [docs/roadmap.md](docs/roadmap.md) for phase status and planned work.
