# nomon-hat Rust Crate Structure

## Overview

`nomon-hat` is a standalone Rust daemon that owns all hardware access on the
Raspberry Pi: I2C, PWM, ADC, GPIO, and UART. It runs as a systemd service
and exposes a Unix domain socket IPC API consumed by the Python `nomon` package
(see [hat_ipc_schema.md](hat_ipc_schema.md)).

This document describes the planned crate layout, module responsibilities,
dependency choices, and configuration options. The `nomon-hat` repository does
not exist yet; this document guides its initial scaffolding when Phase 5 begins.

---

## Repository Layout

```
nomon-hat/                        ← Separate git repository
├── Cargo.toml                    ← Workspace root (optional) or crate root
├── Cargo.lock
├── README.md
├── LICENSE
├── .github/
│   └── workflows/
│       └── ci.yml                ← cross-compile for aarch64
├── src/
│   ├── main.rs                   ← Binary entry point
│   ├── lib.rs                    ← Library root (re-exports public API)
│   ├── config.rs                 ← Configuration (file + env)
│   ├── ipc/
│   │   ├── mod.rs                ← IPC server (Unix socket listener)
│   │   ├── handler.rs            ← Request dispatch
│   │   └── schema.rs             ← Serde types for request/response envelopes
│   ├── hat/
│   │   ├── mod.rs                ← HAT abstraction (Robot HAT V4)
│   │   ├── i2c.rs                ← Low-level I2C helpers (rppal or i2cdev)
│   │   ├── pwm.rs                ← PWM channel control (register writes)
│   │   ├── adc.rs                ← ADC channel reads
│   │   ├── servo.rs              ← Servo abstraction (angle ↔ pulse_us)
│   │   ├── battery.rs            ← Battery voltage via ADC A4
│   │   └── gpio.rs               ← Named GPIO pins (D4-BCM23, MCURST-BCM5, …)
│   └── reset.rs                  ← MCU reset procedure
├── systemd/
│   └── nomon-hat.service         ← systemd unit file
├── scripts/
│   └── deploy.sh                 ← OTA binary deploy (download + SHA256 + atomic swap)
└── tests/
    └── integration_test.rs       ← Integration tests (require hardware)
```

### Library vs Binary Split

The `lib.rs` crate contains all logic (IPC, HAT drivers, config). The
`main.rs` binary is a thin entry point that:

1. Parses `--config` / environment variables into a `Config` struct
2. Initializes the logger
3. Constructs the `Hat` and `IpcServer` instances
4. Runs the `tokio` event loop

Keeping logic in `lib` enables unit tests without spawning a full process and
allows future embedding in other Rust binaries (e.g., a test harness).

---

## Module Descriptions

### `config.rs`

Loads configuration from (in priority order):
1. Command-line arguments (`--i2c-bus`, `--socket-path`, etc.)
2. Environment variables (`NOMON_HAT_*`)
3. Config file at `/etc/nomon-hat/config.toml` (optional)

```rust
pub struct Config {
    pub i2c_bus: u8,                   // default: 1
    pub hat_address: u8,               // default: 0x14
    pub socket_path: PathBuf,          // default: /run/nomon-hat/nomon-hat.sock
    pub socket_mode: u32,              // default: 0o660
    pub log_level: String,             // default: "info"
    pub servo_default_ttl_ms: u64,     // default: 500
    pub watchdog_poll_ms: u64,         // default: 100
}
```

### `ipc/mod.rs` — IPC Server

Listens on the Unix domain socket and accepts concurrent client connections
using `tokio::net::UnixListener`. Each accepted connection runs in its own
`tokio::spawn`ed task.

```
tokio::main
  └─ IpcServer::run()
       └─ loop: accept() → spawn(handle_connection)
            └─ loop: read_line() → dispatch() → write_response()
```

Connection lifecycle:
- On connect: log client PID (from `SO_PEERCRED`)
- On disconnect: release all servo TTL leases held by this connection

### `ipc/schema.rs` — Serde Types

```rust
#[derive(Deserialize)]
pub struct Request {
    pub id: String,
    pub method: String,
    pub params: serde_json::Value,
}

#[derive(Serialize)]
pub struct Response {
    pub id: String,
    pub ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<ErrorPayload>,
}

#[derive(Serialize)]
pub struct ErrorPayload {
    pub code: String,
    pub message: String,
}
```

### `hat/i2c.rs` — I2C Helpers

Thin wrapper around the chosen I2C crate. Provides:
- `read_register(addr, reg, buf)` — write register address, read N bytes
- `write_register(addr, reg, data)` — write register + data bytes

### `hat/pwm.rs` — PWM Controller

Implements Robot HAT V4 PWM register protocol:

| Constant | Value | Purpose |
|----------|-------|---------|
| `REG_CHN` | `0x20` | Channel base register |
| `REG_PSC` | `0x40` | Prescaler (group 1) |
| `REG_ARR` | `0x44` | Auto-reload (period, group 1) |
| `REG_PSC2` | `0x50` | Prescaler (group 2) |
| `REG_ARR2` | `0x54` | Auto-reload (period, group 2) |
| `CLOCK_HZ` | `72_000_000` | PWM clock frequency |
| `PERIOD` | `4095` | Servo PWM period ticks |
| `SERVO_FREQ_HZ` | `50` | Servo PWM frequency |

Prescaler formula: `psc = CLOCK_HZ / (PERIOD + 1) / SERVO_FREQ_HZ - 1`

### `hat/adc.rs` — ADC

Implements Robot HAT V4 ADC command scheme:
1. Write `(7 - channel) | 0x10` to the I2C device
2. Read 2 bytes back; combine as `(high_byte << 8) | low_byte`

### `hat/servo.rs` — Servo Abstraction

Converts angle to pulse width and delegates to `pwm.rs`:

```rust
pub fn angle_to_pulse_us(angle_deg: f32) -> u32 {
    (500.0 + (angle_deg / 180.0) * 2000.0) as u32
}
```

Enforces range: `0.0 ≤ angle_deg ≤ 180.0`, `500 ≤ pulse_us ≤ 2500`.

Manages per-channel TTL leases using a `tokio::time::sleep` watchdog:
when a lease expires, the channel is idled (pulse width set to 0).

### `hat/battery.rs` — Battery Monitor

Reads ADC channel A4 and applies the Robot HAT V4 scaling factor:

```rust
pub fn adc_to_battery_voltage(raw: u16) -> f32 {
    // Convert raw ADC to reference voltage, then scale by 3
    let adc_voltage = (raw as f32) / 65535.0 * 3.3;
    adc_voltage * 3.0
}
```

### `hat/gpio.rs` — Named GPIO Pins

Maps Robot HAT V4 named pins to BCM numbers:

| HAT Name | BCM | Direction | Purpose |
|----------|-----|-----------|---------|
| `D4` | 23 | Output | General digital |
| `D5` | 24 | Output | General digital |
| `MCURST` | 5 | Output | MCU reset |
| `SW` | 19 | Input | User button |
| `LED` | 26 | Output | Status LED |

### `reset.rs` — MCU Reset

```rust
pub async fn reset_mcu(gpio: &Gpio) -> Result<u64, HatError> {
    let mut pin = gpio.get(BCM_MCURST)?.into_output();
    pin.set_low();
    tokio::time::sleep(Duration::from_millis(10)).await;
    pin.set_high();
    Ok(10)
}
```

---

## Dependencies

```toml
[dependencies]
# Async runtime
tokio = { version = "1", features = ["full"] }

# Raspberry Pi hardware access
rppal = "0.19"          # Pure-Rust GPIO/I2C/SPI/UART; no pigpio daemon required

# Serialization
serde = { version = "1", features = ["derive"] }
serde_json = "1"

# Logging
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }

# Configuration
toml = "0.8"            # Config file parsing
clap = { version = "4", features = ["derive"] }  # CLI args

# Error handling
thiserror = "1"

[dev-dependencies]
# Test helpers
tokio-test = "0.4"
tempfile = "3"
```

### Dependency Rationale

| Crate | Reason |
|-------|--------|
| `tokio` | Async I/O for concurrent IPC connections without OS threads per client; `time` feature for TTL watchdog timers |
| `rppal` | Pure-Rust Pi GPIO/I2C/SPI — no `pigpio` daemon required, deterministic latency, safe memory model |
| `serde` + `serde_json` | Standard Rust JSON serialization; zero-copy deserialization for small IPC messages |
| `tracing` | Structured async-aware logging; integrates with `tokio` spans |
| `toml` | Config file format consistent with Cargo; human-readable |
| `clap` | Ergonomic CLI argument parsing with derive macros |
| `thiserror` | Ergonomic custom error types without boilerplate |

**Not included:**
- `axum` / `hyper` — localhost HTTP fallback is deferred; Unix socket IPC is preferred (see ADR-006)
- `tokio-serial` — UART not needed for Robot HAT V4 first milestone

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NOMON_HAT_I2C_BUS` | `1` | Linux I2C bus number |
| `NOMON_HAT_ADDRESS` | `0x14` | Robot HAT I2C device address |
| `NOMON_HAT_SOCKET_PATH` | `/run/nomon-hat/nomon-hat.sock` | Unix socket path |
| `NOMON_HAT_SOCKET_MODE` | `0660` | Socket file permissions (octal) |
| `NOMON_HAT_LOG_LEVEL` | `info` | Log level (`trace`, `debug`, `info`, `warn`, `error`) |
| `NOMON_HAT_SERVO_DEFAULT_TTL_MS` | `500` | Default servo lease TTL in milliseconds |
| `NOMON_HAT_WATCHDOG_POLL_MS` | `100` | TTL watchdog polling interval in milliseconds |

### Config File (`/etc/nomon-hat/config.toml`)

```toml
i2c_bus = 1
hat_address = 0x14
socket_path = "/run/nomon-hat/nomon-hat.sock"
socket_mode = 0o660
log_level = "info"
servo_default_ttl_ms = 500
watchdog_poll_ms = 100
```

---

## systemd Unit (`systemd/nomon-hat.service`)

```ini
[Unit]
Description=nomon HAT hardware daemon
After=network.target

[Service]
Type=simple
User=root
Group=nomon
ExecStart=/usr/local/bin/nomon-hat --config /etc/nomon-hat/config.toml
Restart=on-failure
RestartSec=2s
RuntimeDirectory=nomon-hat
RuntimeDirectoryMode=0755

[Install]
WantedBy=multi-user.target
```

---

## Cross-Compilation (CI)

The nomon-hat CI workflow cross-compiles for `aarch64-unknown-linux-gnu` using
the [`cross`](https://github.com/cross-rs/cross) tool:

```yaml
# .github/workflows/ci.yml (excerpt)
- name: Build aarch64 binary
  run: |
    cargo install cross --version 0.2.5
    cross build --release --target aarch64-unknown-linux-gnu
```

The resulting binary is uploaded as a GitHub release artifact and referenced
in the OTA job document (Phase 6).

---

## First Milestone Scope

For the initial `nomon-hat` v0.1.0 release, implement only:

| Module | Priority | Notes |
|--------|----------|-------|
| `config.rs` | P0 | Required for all modules |
| `ipc/` | P0 | Required for Python integration |
| `hat/i2c.rs` | P0 | Foundation for all HAT comms |
| `hat/adc.rs` | P0 | Battery voltage |
| `hat/battery.rs` | P0 | Battery voltage |
| `hat/pwm.rs` | P0 | Servo control |
| `hat/servo.rs` | P0 | Servo control |
| `hat/gpio.rs` | P1 | MCU reset only |
| `reset.rs` | P1 | MCU reset |

`P0` = battery + servo milestone. `P1` = MCU reset, nice-to-have for first release.
