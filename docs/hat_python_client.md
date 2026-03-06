# nomon.hat — Python Client Module

## Overview

`nomon.hat` is a thin Python module that connects `nomon.api` to the
`nomon-hat` Rust daemon over the Unix domain socket IPC defined in
[hat_ipc_schema.md](hat_ipc_schema.md).

**Key design principle:** The Python client contains *no register logic*. It
does not know about I2C addresses, PWM prescalers, ADC scaling, or servo
pulse widths. All hardware knowledge lives in `nomon-hat` (Rust). The Python
client only:

1. Opens and manages the socket connection
2. Serialises/deserialises NDJSON request and response envelopes
3. Exposes typed methods for each IPC method
4. Raises Python exceptions on IPC or hardware errors

---

## Module Location

```
src/nomon/
└── hat.py          ← HatClient class (this module)
```

The module follows the same pattern as `nomon.camera`, `nomon.telemetry`, etc.:
one file, one class, conditional import for the optional socket path.

---

## Class Interface

```python
class HatClient:
    """Client for the nomon-hat Unix domain socket IPC daemon.

    Parameters
    ----------
    socket_path : str | Path, optional
        Path to the Unix domain socket. Defaults to ``/run/nomon-hat/nomon-hat.sock``
        or the value of the ``NOMON_HAT_SOCKET_PATH`` environment variable.
    timeout_s : float, optional
        Per-request read timeout in seconds. Default: 2.0.
    """

    def __init__(
        self,
        socket_path: str | Path | None = None,
        timeout_s: float = 2.0,
    ) -> None: ...

    # ------------------------------------------------------------------ #
    # Connection management                                                #
    # ------------------------------------------------------------------ #

    def connect(self) -> None:
        """Open the socket connection to nomon-hat.

        Raises
        ------
        HatConnectionError
            If the socket file does not exist or the connection is refused.
        """

    def close(self) -> None:
        """Close the socket connection. Safe to call when already closed."""

    def __enter__(self) -> "HatClient": ...
    def __exit__(self, *args: object) -> None: ...

    # ------------------------------------------------------------------ #
    # Typed methods                                                        #
    # ------------------------------------------------------------------ #

    def health(self) -> HatHealthResult:
        """Return daemon liveness and hardware status.

        Returns
        -------
        HatHealthResult
            Dataclass with fields: status, version, hat_address, i2c_bus,
            uptime_s.

        Raises
        ------
        HatError
            If the daemon returns ok=false.
        HatConnectionError
            If the socket connection is lost.
        """

    def get_battery_voltage(self) -> float:
        """Read battery voltage via Robot HAT V4 ADC channel A4.

        Returns
        -------
        float
            Battery voltage in volts.

        Raises
        ------
        HatError
            On hardware read failure.
        """

    def set_servo_pulse_us(
        self,
        channel: int,
        pulse_us: int,
        ttl_ms: int = 500,
    ) -> None:
        """Set a PWM channel to a specific pulse width in microseconds.

        Parameters
        ----------
        channel : int
            PWM channel number (0–11).
        pulse_us : int
            Pulse width in microseconds (500–2500).
        ttl_ms : int, optional
            Lease TTL in milliseconds. The daemon idles the servo if not
            refreshed within this interval. Default: 500.

        Raises
        ------
        ValueError
            If channel or pulse_us is out of range.
        HatError
            On hardware write failure.
        """

    def set_servo_angle(
        self,
        channel: int,
        angle_deg: float,
        ttl_ms: int = 500,
    ) -> None:
        """Set a servo to an angle in degrees.

        Parameters
        ----------
        channel : int
            PWM channel number (0–11).
        angle_deg : float
            Target angle (0.0–180.0 degrees).
        ttl_ms : int, optional
            Lease TTL in milliseconds. Default: 500.

        Raises
        ------
        ValueError
            If channel or angle_deg is out of range.
        HatError
            On hardware write failure.
        """

    def reset_mcu(self) -> None:
        """Assert and release the Robot HAT V4 MCU reset line.

        Raises
        ------
        HatError
            On GPIO failure.
        """
```

---

## Exception Hierarchy

```python
class HatError(Exception):
    """Base exception for all nomon.hat errors.

    Attributes
    ----------
    code : str
        Machine-readable error code from the IPC schema (e.g.
        ``"HARDWARE_ERROR"``), or ``"CLIENT_ERROR"`` for client-side issues.
    message : str
        Human-readable description.
    """
    code: str
    message: str


class HatConnectionError(HatError):
    """Raised when the socket connection to nomon-hat cannot be established
    or is lost during a request.

    code is always ``"CONNECTION_ERROR"``.
    """


class HatTimeoutError(HatError):
    """Raised when a request does not receive a response within timeout_s.

    code is always ``"TIMEOUT"``.
    """
```

---

## Internal Architecture

### Connection Management

`HatClient` maintains a single persistent Unix domain socket connection:

```
HatClient
├── _sock: socket.socket | None
├── _rfile: io.BufferedReader | None    ← buffered reader for readline()
└── _lock: threading.Lock               ← serialise concurrent requests
```

- **Lazy connect**: `connect()` is called automatically on first request if
  not already connected.
- **Reconnect on error**: if the socket raises `ConnectionResetError` or
  `BrokenPipeError`, `HatClient` reconnects once and retries the request.
  If the retry also fails, `HatConnectionError` is raised.
- **Thread safety**: `_lock` serialises concurrent method calls from multiple
  threads (e.g., REST route handlers). No async I/O is used in the client —
  FastAPI route handlers call `asyncio.to_thread(client.set_servo_angle, ...)`.

### Request/Response Flow

```python
def _request(self, method: str, params: dict) -> dict:
    req = {"id": self._next_id(), "method": method, "params": params}
    line = json.dumps(req) + "\n"
    self._sock.sendall(line.encode())
    resp_line = self._rfile.readline()   # blocks until \n
    resp = json.loads(resp_line)
    if not resp["ok"]:
        raise HatError(resp["error"]["code"], resp["error"]["message"])
    return resp["result"]
```

### ID Generation

IDs are sequential integers formatted as strings (`"1"`, `"2"`, …). The
counter resets on reconnect. IDs are opaque to the daemon and only used for
correlation in logs.

---

## Usage Examples

### Basic usage (context manager)

```python
from nomon.hat import HatClient

with HatClient() as hat:
    voltage = hat.get_battery_voltage()
    print(f"Battery: {voltage:.2f} V")

    hat.set_servo_angle(channel=0, angle_deg=90.0)
```

### Background servo refresh loop

```python
import asyncio
from nomon.hat import HatClient

async def hold_angle(hat: HatClient, channel: int, angle: float) -> None:
    """Refresh servo position every 200 ms to keep TTL alive."""
    while True:
        await asyncio.to_thread(hat.set_servo_angle, channel, angle, ttl_ms=500)
        await asyncio.sleep(0.2)
```

### Integration with nomon.api (FastAPI route handler)

```python
# In nomon/api.py — HAT endpoint example
from nomon.hat import HatClient, HatConnectionError, HatError

_hat_client: HatClient | None = None

@app.get("/api/hat/battery")
async def get_battery() -> dict:
    if _hat_client is None:
        raise HTTPException(503, "nomon-hat daemon not available")
    try:
        voltage = await asyncio.to_thread(_hat_client.get_battery_voltage)
        return {"voltage_v": voltage, "timestamp": utc_now()}
    except HatConnectionError as e:
        raise HTTPException(503, str(e)) from e
    except HatError as e:
        raise HTTPException(500, str(e)) from e
```

### Daemon availability check at startup

```python
from nomon.hat import HatClient, HatConnectionError

def probe_hat_daemon(socket_path: str) -> bool:
    """Return True if nomon-hat is running and reachable."""
    try:
        with HatClient(socket_path=socket_path) as hat:
            result = hat.health()
            return result.status == "ok"
    except HatConnectionError:
        return False
```

---

## Testing Strategy

The HAT client must be testable on Windows/macOS (no Raspberry Pi required).

### Mock socket server (pytest fixture)

```python
# tests/conftest.py
import socket, threading, json, tempfile, os, pytest

@pytest.fixture
def mock_hat_socket(tmp_path):
    """Start a minimal fake nomon-hat server in a background thread."""
    sock_path = str(tmp_path / "nomon-hat.sock")

    def _server():
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(sock_path)
        srv.listen(1)
        conn, _ = srv.accept()
        for line in conn.makefile():
            req = json.loads(line)
            if req["method"] == "health":
                resp = {"id": req["id"], "ok": True,
                        "result": {"status": "ok", "version": "0.1.0"}}
            elif req["method"] == "get_battery_voltage":
                resp = {"id": req["id"], "ok": True,
                        "result": {"voltage_v": 7.5, "raw_adc": 25000}}
            else:
                resp = {"id": req["id"], "ok": False,
                        "error": {"code": "UNKNOWN_METHOD",
                                  "message": f"No method '{req['method']}'"}}
            conn.sendall((json.dumps(resp) + "\n").encode())
        conn.close()
        srv.close()

    t = threading.Thread(target=_server, daemon=True)
    t.start()
    yield sock_path

def test_get_battery_voltage(mock_hat_socket):
    from nomon.hat import HatClient
    with HatClient(socket_path=mock_hat_socket) as hat:
        v = hat.get_battery_voltage()
    assert v == pytest.approx(7.5)
```

All `HatClient` tests use this fixture — no hardware required.

---

## What NOT to Put in This Module

- I2C register addresses or ADC scaling formulae — that belongs in `nomon-hat`
- PWM prescaler calculations — that belongs in `nomon-hat`
- GPIO BCM pin numbers — that belongs in `nomon-hat`
- Retry logic for hardware errors — let `HatError` propagate up to the caller
- Business logic (e.g., "low battery warning") — belongs in `nomon.api` routes
