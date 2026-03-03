# Microcontroller Setup


## Install Software


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