# Microcontroller Setup


## Hardware

**Device:** Raspberry Pi Zero 2 W running Debian GNU/Linux 13 (trixie)  
**Camera:** OV5647 (Pi Camera v1.3) via FPC ribbon cable  
**HAT:** SunFounder Robot HAT V4


## Robot HAT V4 Hardware Discovery

### I2C Bus Scan

The Robot HAT V4 controller is found on **I2C bus 1, address 0x14**:

```bash
sudo i2cdetect -y 1
```

```
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:                         -- -- -- -- -- -- -- -- --
10: -- -- -- -- 14 -- -- -- -- -- -- -- -- -- -- --
```

I2C buses 10 and 11 (muxed) show `0x36` as `UU` (in-use by kernel driver) —
these are the OV5647 camera sensor buses and should not be touched.

SPI nodes `/dev/spidev0.0` and `/dev/spidev0.1` exist, but the Robot HAT V4
is primarily an I2C device. SPI is available for future expansion.

### Robot HAT V4 Register Map

Derived from
[sunfounder/robot-hat commit d856cfb](https://github.com/sunfounder/robot-hat/commit/d856cfb67f06e69150bbbb58e750f1db3097c39d):

| Constant | Value | Purpose |
|----------|-------|---------|
| `REG_CHN` | `0x20` | PWM channel base register |
| `REG_PSC` | `0x40` | Prescaler (PWM group 1) |
| `REG_ARR` | `0x44` | Auto-reload / period (group 1) |
| `REG_PSC2` | `0x50` | Prescaler (PWM group 2) |
| `REG_ARR2` | `0x54` | Auto-reload / period (group 2) |
| `CLOCK_HZ` | 72 MHz | PWM controller clock |
| `PERIOD` | 4095 | Servo PWM period ticks |
| `SERVO_FREQ` | 50 Hz | Standard servo frequency |

Servo pulse width range: **500–2500 µs** (0°–180°).

Battery ADC: channel **A4**, command `(7 - 4) | 0x10 = 0x13`, scaling
`battery_v = adc_voltage × 3`.

Named GPIO pins:

| HAT Name | BCM | Direction |
|----------|-----|-----------|
| `D4` | 23 | Output |
| `D5` | 24 | Output |
| `MCURST` | 5 | Output (MCU reset) |
| `SW` | 19 | Input |
| `LED` | 26 | Output |

MCU reset procedure: assert BCM5 low for ≥ 10 ms, then high.

All hardware control is implemented in the **nomon-hat Rust daemon** (Phase 5).
The Python `nomon` package communicates with it via IPC only — it does not
write I2C registers or toggle GPIO directly. See
[hat_ipc_schema.md](hat_ipc_schema.md).

---


### Install Tailscale

Use `curl` to install Tailscale:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
```


### Install `uv`

Use `curl` to install `uv`

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```


### Install `nomon`

Clone the `nomon` repository, then run `uv sync`:

```bash
cd ~
git clone https://github.com/Perceptua/nomon.git
cd ~/nomon
uv sync
```


### Run Server

To start the API server on the Raspberry Pi device, activate the virtual environment using

```bash
cd ~/nomon
source .venv/bin/activate
```

Then run `python3` to open a Python shell. In the shell, run

```python3
from nomon.api import APIServer
server = APIServer(host="0.0.0.0", port=8443)
thread = server.start_background()
```

The server should announce it is running on port 8443. To verify remote connectivity, find the device IP in [Tailscale](https://login.tailscale.com/admin/machines), then open a browser on a remote machine & go to `https://<tailscale_ip>:8443/docs/`.


---


## Install and Run `nomon-hat` Daemon (Phase 5)

The `nomon-hat` Rust daemon owns all Robot HAT V4 hardware access. The Python
`nomon` package connects to it via a Unix domain socket. The daemon must be
running before any HAT endpoints are used.

### One-time device setup

```bash
# Create the nomon group and add the nomon user
sudo groupadd -r nomon
sudo usermod -aG nomon pi        # replace 'pi' with your nomon service user
```

### Install the binary

Download the latest `nomon-hat` release binary for `aarch64-unknown-linux-gnu`
from the nomon-hat GitHub Releases page and install it:

```bash
# Example — replace <version> and <sha256> with actual release values
curl -LO https://github.com/Perceptua/nomon-hat/releases/download/v<version>/nomon-hat
echo "<sha256>  nomon-hat" | sha256sum --check
chmod +x nomon-hat
sudo mv nomon-hat /usr/local/bin/nomon-hat
```

### Configure

Create the config file:

```bash
sudo mkdir -p /etc/nomon-hat
sudo tee /etc/nomon-hat/config.toml <<'EOF'
i2c_bus = 1
hat_address = 0x14
socket_path = "/run/nomon-hat/nomon-hat.sock"
socket_mode = 0o660
log_level = "info"
servo_default_ttl_ms = 500
EOF
```

### Install the systemd service

```bash
# Download the unit file from the nomon-hat repo
sudo curl -o /etc/systemd/system/nomon-hat.service \
  https://raw.githubusercontent.com/Perceptua/nomon-hat/main/systemd/nomon-hat.service
sudo systemctl daemon-reload
sudo systemctl enable nomon-hat
sudo systemctl start nomon-hat
```

### Verify

```bash
# Check service status
sudo systemctl status nomon-hat

# Send a health request manually (requires socat)
echo '{"id":"1","method":"health","params":{}}' | \
  socat - UNIX-CONNECT:/run/nomon-hat/nomon-hat.sock
# Expected: {"id":"1","ok":true,"result":{"status":"ok",...}}
```

### Configure nomon to use the socket

Set the socket path in the nomon environment file if it differs from the
default `/run/nomon-hat/nomon-hat.sock`:

```bash
# /home/pi/nomon/.env (example)
NOMON_HAT_SOCKET_PATH=/run/nomon-hat/nomon-hat.sock
```

nomon will surface `503 Service Unavailable` from any `/api/hat/...` endpoint
if the daemon is not running or the socket does not exist.

See [hat_ipc_schema.md](hat_ipc_schema.md) for the full IPC protocol and
[nomon_hat_crate.md](nomon_hat_crate.md) for the Rust crate structure.