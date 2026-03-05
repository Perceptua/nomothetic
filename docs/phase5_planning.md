# Phase 5 Planning: Rust HAT Drivers, Repo Strategy & AWS IoT

## Summary

This document records the architectural decisions made during planning for
Phase 5 (HAT module drivers) and the future OTA update strategy. Three
questions were evaluated:

1. Would converting existing Python modules to Rust improve performance?
2. Should the project be split into multiple repositories?
3. How does AWS IoT affect the OTA update strategy?

---

## 1 — Python-to-Rust Conversion Analysis

Each module was assessed for whether Rust would deliver meaningful performance
or binary-size benefits over the current Python implementation.

| Module | Bottleneck | Rust Benefit |
|---|---|---|
| `nomon.camera` | libcamera (C++) via picamera2 | **None** — would be FFI to the same native code |
| `nomon.streaming` | Camera sensor frame rate | **None** — Flask is not the constraint |
| `nomon.api` | Camera hardware + network latency | **Marginal** — smaller RSS and faster cold start on Pi |
| `nomon.telemetry` | Network I/O + sleep interval | **None** — pure I/O wait |
| `nomon.updater` | External process I/O (git, systemctl) | **None** — Python is not the bottleneck |

### Conclusion

A full Rust conversion is not justified. The project's performance profile is
almost entirely hardware I/O-bound or delegates to native libraries (libcamera).
Python's overhead is not the limiting factor in any existing module.

The one module with a credible (though not overwhelming) Rust case is
`nomon.api` — running FastAPI + uvicorn + picamera2 + paho-mqtt together
consumes ~80–150 MB RSS on a 512 MB Pi Zero, whereas a Rust binary (axum)
would use ~5–15 MB. However, the cost of losing picamera2 FFI, Pydantic
models, OpenAPI auto-generation (ADR-002), and adding ARM cross-compilation
to the Windows/macOS dev workflow far outweighs the RSS savings.

### Phase 5 Exception

HAT/sensor drivers are the one area where Rust has a **genuine case**. If
hardware requires tight-latency GPIO toggling, SPI burst transfers, or
deterministic timing (microsecond-precision protocols), Python's GIL and
interpreter overhead become real constraints. Rust with `rppal` (a pure-Rust
Raspberry Pi GPIO/SPI/I2C crate) delivers memory safety and deterministic
latency without a daemon dependency like `pigpio`.

**Decision:** Phase 5 HAT drivers will be implemented in Rust in a separate
repository (`nomon-hat`). See ADR-006.

---

## 2 — Repository Strategy

### Why the Python Monorepo Must Stay Together

The OTA `UpdateManager` (Phase 4) updates a device by executing
`git fetch + reset --hard` on a **single git repository**, then restarts one
systemd service. The update unit is the repository — everything in it moves
atomically to a new SHA.

Splitting any Python module into its own repo would require:

- A second manifest URL + second `UpdateManager` instance per device
- Two independent `git reset --hard` operations with no atomicity guarantee —
  the device can be transiently in a mixed-version state
- Cross-repo version pinning in `pyproject.toml` (manual maintenance + CI)
- The pre-flight `import nomon` check would no longer validate the whole system

None of the Python modules have external consumers or independent release
cadences, so there is zero benefit to splitting them.

### Why the Rust HAT Code Is a Separate Repo

1. **Different build artifact** — compiled `aarch64-unknown-linux-gnu` binary,
   not a pip-installable package
2. **Different update pipeline** — binary artifact download + SHA-256 verify +
   atomic file swap (not `git reset --hard`)
3. **Different systemd service** — runs as `nomon-hat.service`, independent of
   `nomon.service`
4. **Different release cadence** — HAT firmware changes independently of the
   Python REST API

### Final Layout

```
nomon/              ← Python monorepo (this repo — keep everything here)
  nomon.camera
  nomon.streaming
  nomon.api
  nomon.telemetry
  nomon.updater

nomon-hat/          ← Separate Rust repo (Phase 5)
  Cargo.toml
  src/main.rs       ← HAT daemon
  systemd/          ← nomon-hat.service unit file
  scripts/          ← OTA binary deploy script
```

### Interface Between Rust and Python

`nomon.api` communicates with `nomon-hat` via a local IPC mechanism. Preferred
options in order:

1. **Unix domain socket** — Rust listens on `/run/nomon-hat.sock`;
   `nomon.api` sends JSON requests. No port allocation, low overhead,
   OS-enforced process isolation.
2. **Localhost HTTP** — Rust runs an axum server on `127.0.0.1:8444`;
   `nomon.api` calls it with `httpx`. More overhead but easier to inspect
   with curl during development.

The interface contract (JSON schema) is documented in `docs/architecture.md`
as a cross-repo API boundary.

---

## 3 — AWS IoT for OTA Updates

### AWS IoT Jobs (Recommended Tier)

IoT Jobs is a task-dispatch service built on IoT Core (MQTT broker). The
management server publishes a job document to a device's reserved MQTT topic;
the device subscribes, executes the job, and reports status back.

**Multi-repo coordination:** A single job document can specify versions for
both the Python package and the Rust binary simultaneously:

```json
{
  "nomon_version": "0.5.0",
  "nomon_git_sha": "abc123",
  "nomon_hat_version": "1.2.0",
  "nomon_hat_artifact_url": "s3://...",
  "nomon_hat_sha256": "def456"
}
```

This solves the mixed-version transient state problem — one job = one atomic
fleet intent.

**What changes on-device:**

| Concern | Current (`nomon.updater`) | With AWS IoT Jobs |
|---|---|---|
| Update trigger | Poll manifest URL (pull) | IoT Core MQTT push |
| Update mechanism | `git fetch + reset --hard` | S3 artifact download |
| Verification | git SHA + import check | SHA-256 + health check |
| Multi-repo coord | Not supported | Job document JSON |
| Rollback | `git reset --hard` | Job failure report + script |
| Telemetry broker | Any MQTT broker | AWS IoT Core (same paho-mqtt) |
| On-device extra | Nothing (stdlib only) | AWS IoT Device SDK (~5 MB) |

**Migration path:** `nomon.telemetry` already has MQTT connection logic via
`paho-mqtt`; the IoT Jobs subscription adds a second topic on the same broker
connection, using X.509 certificate auth instead of username/password.

### AWS IoT Greengrass v2 (Not Recommended)

Greengrass provides the strongest multi-repo coordination (full component
lifecycle management with deployment-level rollback), but requires a JVM
runtime that consumes ~150–250 MB RAM — a deal-breaker on Pi Zero 2W (512 MB).

**Decision:** If AWS IoT is adopted, use IoT Jobs (not Greengrass). See ADR-007.
