# ADR-005 — paho-mqtt for MQTT Telemetry

## Status

Accepted

## Context

Phase 3 requires each Raspberry Pi node to publish structured telemetry to a
centralized MQTT broker. We need a Python MQTT client library.

The project philosophy prefers the Python standard library where possible.
MQTT is not covered by the standard library, so a third-party package is
required.

Candidate libraries:

| Library | Stars (approx.) | Notes |
|---|---|---|
| **paho-mqtt** | 2.2 k+ | Eclipse Foundation; de facto standard; MQTTv5 & v3.1.1 |
| gmqtt | ~500 | asyncio-based; less commonly used |
| aiomqtt | ~700 | asyncio wrapper around paho; adds async overhead |
| hbmqtt | ~700 | Unmaintained since 2020 |

## Decision

Use **paho-mqtt >= 2.0** (the Eclipse Paho Python MQTT client).

Specifically, target the **2.x API** which introduced `CallbackAPIVersion` to
clarify callback signatures and deprecated legacy positional arguments.

## Rationale

- **De facto standard** — paho-mqtt is the canonical Python MQTT client,
  recommended by the MQTT specification authors and the Eclipse Foundation.
- **Well documented** — extensive official documentation and community resources.
- **Actively maintained** — regular releases; 2.x published 2024.
- **MQTTv5 support** — future-proof for broker features like message expiry,
  user properties, and reason codes.
- **No async requirement** — nomon telemetry uses a daemon background thread,
  not an async event loop, so a synchronous client is appropriate.
- **Minimal footprint** — paho-mqtt has no transitive dependencies.
- **Conditional import** — follows the existing pattern from `nomon.camera`
  (picamera2) and `nomon.streaming` (Flask): the module is importable without
  paho-mqtt installed; `ImportError` is raised at instantiation only.

## Consequences

- A new `[telemetry]` optional dependency group is added to `pyproject.toml`.
- `paho-mqtt` is also added to `[dev]` so tests run without a separate install step.
- Tests mock `nomon.telemetry.mqtt` via `unittest.mock.patch` — no real broker
  is required during testing; all 86 tests pass on Windows without a Pi.
- The 2.x callback API (`CallbackAPIVersion.VERSION2`) is used throughout;
  the 1.x positional callback style is not supported.
