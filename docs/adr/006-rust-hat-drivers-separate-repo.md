# ADR-006: Rust for HAT/Sensor Drivers in a Separate Repository

**Status:** Accepted  
**Date:** 2026-03-05  
**Deciders:** Perceptua  

---

## Context

Phase 5 introduces HAT module and sensor drivers. These drivers may require
tight-latency GPIO toggling, SPI burst transfers, or protocols with
microsecond-precision timing. The project currently uses Python for all
modules, and a Python-to-Rust conversion was evaluated for every module.

Options evaluated for Phase 5 driver implementation:

1. **Python in this repo** — follow the `Camera` pattern with conditional
   imports for `spidev`, `gpiozero`, `pigpio`
2. **Rust in this repo** — mixed-language monorepo with Cargo + setuptools
3. **Rust in a separate repo** — standalone Rust daemon, communicates with
   `nomon.api` via local IPC

## Decision

Implement HAT/sensor drivers in **Rust in a separate repository** (`nomon-hat`),
running as its own systemd service (`nomon-hat.service`). Communication with
`nomon.api` occurs over a **local Unix domain socket** (preferred) or localhost
HTTP as a fallback.

## Rationale

### Why Rust (not Python) for HAT drivers

- Python's GIL and interpreter overhead create non-deterministic latency in
  GPIO and SPI timing-critical operations — even with `pigpio` as a C backend
- Rust with `rppal` provides pure-Rust GPIO/SPI/I2C access with deterministic
  latency and memory safety, without requiring a daemon like `pigpio`
- Compiled binary footprint (~5–15 MB) is far smaller than the Python
  interpreter + dependencies required for equivalent hardware access
- No performance benefit was found for any of the existing Python modules
  (`camera`, `streaming`, `api`, `telemetry`, `updater`) — their bottlenecks
  are hardware I/O, native libraries, or network latency, not Python overhead.
  Rust conversion is only justified for the HAT driver layer

### Why a separate repo (not a mixed-language monorepo)

- **Different build artifact**: a compiled `aarch64-unknown-linux-gnu` binary
  has nothing in common with `pip install -e .`
- **Different update pipeline**: the binary is deployed via artifact download +
  SHA-256 verification + atomic file swap, not `git fetch + reset --hard`
  (the current `UpdateManager` strategy)
- **Different systemd service**: `nomon-hat.service` has an independent
  lifecycle from `nomon.service`
- **Different release cadence**: HAT firmware may change independently of the
  Python REST API; coupling them in one repo would force unnecessary
  co-releases
- **Existing Python modules must stay together**: the `UpdateManager` OTA
  strategy (Phase 4) relies on a single-repo atomic update via
  `git reset --hard`. Splitting any Python module out would break the atomicity
  guarantee and require a dual-manifest update mechanism

### Why the Python modules are NOT split

Every Python module was evaluated for independent-repo viability:

| Module | Coupling | Split benefit |
|---|---|---|
| `nomon.camera` | Used by `api` + `streaming` | None — breaks dep graph |
| `nomon.streaming` | Depends on `nomon.camera` | None |
| `nomon.api` | Central hub; depends on `camera` | None |
| `nomon.telemetry` | Depends on `nomon.__version__` | None — too lightweight |
| `nomon.updater` | Depends on `nomon.__version__` | None — Pi/systemd-specific |

No Python module has external consumers or an independent release cadence.

## Interface Contract

`nomon.api` communicates with the `nomon-hat` daemon via a local IPC mechanism:

1. **Preferred**: Unix domain socket at `/run/nomon-hat.sock` using a JSON
   request/response protocol
2. **Fallback**: Localhost HTTP at `http://127.0.0.1:8444`

The JSON schema for this interface will be documented in `docs/architecture.md`
when the HAT hardware is identified. `nomon.api` will expose HAT operations
under `/api/hat/...` endpoints that proxy to the Rust daemon.

## Consequences

- A new `nomon-hat` repository will be created when Phase 5 begins
- The `nomon-hat` build produces a cross-compiled ARM binary (CI must include
  `cross` or equivalent ARM cross-compilation tooling)
- OTA updates for `nomon-hat` use artifact-based deployment (not git-based),
  coordinated via a job document if AWS IoT Jobs is adopted (see ADR-007)
- `nomon.api` gains a dependency on the local IPC socket — HAT endpoints
  return `503 Service Unavailable` if `nomon-hat` is not running
- Phase 5 in the roadmap is updated to reflect Rust + separate repo
