# ADR-007: AWS IoT Jobs for Fleet OTA Updates (Future)

**Status:** Proposed  
**Date:** 2026-03-05  
**Deciders:** Perceptua  

---

## Context

Phase 4 introduced `nomon.updater.UpdateManager`, which polls a JSON version
manifest via HTTP and applies updates using `git fetch + reset --hard`. This
works for a single Python repository but cannot coordinate updates across
multiple repositories (e.g., the Python `nomon` package and the Rust
`nomon-hat` binary introduced in ADR-006).

AWS IoT provides two managed OTA services:

1. **AWS IoT Jobs** — lightweight task dispatch over MQTT; device subscribes
   to a reserved topic, receives job documents, executes them, reports status
2. **AWS IoT Greengrass v2** — full on-device component runtime with lifecycle
   management; requires a JVM (Java 11+) on the device

## Decision

When the project adopts AWS IoT services, use **AWS IoT Jobs** for fleet OTA
updates. Do **not** adopt Greengrass v2 due to its JVM memory requirements on
Pi Zero-class hardware.

## Rationale

### Why IoT Jobs

- **Push-based updates**: the management server publishes a job to the device's
  MQTT topic — no polling interval delay. Replaces the current
  `urllib.request` polling loop
- **Multi-repo coordination**: a single job document can specify versions for
  both `nomon` (Python) and `nomon-hat` (Rust) simultaneously:
  ```json
  {
    "nomon_version": "0.5.0",
    "nomon_git_sha": "abc123",
    "nomon_hat_version": "1.2.0",
    "nomon_hat_artifact_url": "s3://...",
    "nomon_hat_sha256": "def456"
  }
  ```
  One job = one atomic fleet intent, solving the mixed-version transient state
  problem
- **Artifact-based delivery**: updates download pre-built artifacts from S3
  (replacing `git fetch + reset --hard`), which is strictly better for
  production — deploying a known-good build artifact rather than running git
  on the device
- **Reuses existing infrastructure**: `nomon.telemetry` already uses
  `paho-mqtt` (ADR-005) for MQTT connectivity; IoT Jobs adds a second topic
  subscription on the same broker connection, pointing to AWS IoT Core with
  X.509 certificate auth
- **Minimal footprint**: AWS IoT Device SDK for Python adds ~5 MB; no JVM
  or heavy runtime required

### Why not Greengrass v2

- Greengrass Nucleus requires a JVM (Java 11+), consuming ~150–250 MB RAM at
  idle
- On Pi Zero 2W (512 MB total RAM), this leaves insufficient headroom for the
  camera pipeline, FastAPI, and the Rust HAT daemon simultaneously
- Greengrass's component lifecycle management is valuable for large fleets
  with complex component graphs, but overkill for a small private fleet with
  two components

### Migration path from current `nomon.updater`

| Concern | Current | With AWS IoT Jobs |
|---|---|---|
| Update trigger | HTTP poll (`urllib.request`) | MQTT push (IoT Core topic) |
| Update mechanism | `git fetch + reset --hard` | S3 artifact download |
| Verification | git SHA + `import nomon` pre-flight | SHA-256 + health check |
| Multi-repo coordination | Not supported | Job document JSON |
| Rollback | `git reset --hard <prev_hash>` | Job failure report + rollback script |
| Telemetry broker | Any MQTT broker | AWS IoT Core (same paho-mqtt) |
| On-device extra | Nothing (stdlib only) | AWS IoT Device SDK (~5 MB) |

## Trade-offs

- Introduces a dependency on AWS IoT Core — the management server must use
  AWS infrastructure (or a compatible MQTT broker)
- X.509 certificate provisioning replaces the current Tailscale-only trust
  model; each device needs a unique certificate and private key
- `nomon.updater` would be significantly rewritten or replaced — the
  `git fetch + reset --hard` mechanism is retired in favor of artifact download
- Vendor lock-in concern: IoT Jobs API is AWS-specific. However, the
  on-device logic (subscribe to topic, download artifact, verify, restart) is
  generic enough to adapt to any MQTT-based job dispatcher

## Consequences

- This ADR is **Proposed**, not yet Accepted — it will be accepted when the
  project begins integrating AWS IoT services
- When accepted, `nomon.updater` will be refactored to:
  1. Subscribe to the AWS IoT Jobs MQTT topic
  2. Receive job documents instead of polling a manifest URL
  3. Download artifacts from S3 URLs
  4. Verify SHA-256 checksums
  5. Apply updates (Python package + Rust binary)
  6. Report job success/failure back over MQTT
- The existing REST endpoints (`/api/system/version`,
  `/api/system/update/status`, `/api/system/update/apply`) will be preserved
  with the same response schemas
- `nomon.telemetry` may be consolidated to use the same AWS IoT Core
  connection for both telemetry publishing and job subscription
