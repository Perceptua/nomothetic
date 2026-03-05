# Phase 4 Completion Summary: OTA Update Mechanism

## Overview

**Phase 4 is complete.** Each nomon device can now poll a remote version manifest,
detect available updates, and apply them via `git reset --hard` + systemd restart —
all without manual SSH access.  A pre-flight import check protects against applying
broken code; if it fails, the repository is automatically rolled back before any
restart is attempted.

---

## What Was Built

### Technology Stack

- **Python standard library only** — `urllib.request` (HTTP), `subprocess` (git + systemd),
  `hashlib` (SHA-256), `threading` — **zero new runtime dependencies**

### `nomon.updater` — `UpdateManager`

| Feature | Description |
|---------|-------------|
| Background thread | Daemon thread; does not block the REST API |
| Manifest polling | `urllib.request` GET → JSON parse → version compare |
| Notify-only default | `NOMON_UPDATE_AUTO_APPLY=true` required to auto-apply |
| Update procedure | `git fetch --tags origin` + `git reset --hard <ref>` |
| SHA verification | HEAD SHA compared against manifest `git_sha` field |
| Pre-flight check | `python -c "import nomon"` in a fresh subprocess |
| Rollback on failure | `git reset --hard <prev_hash>` if SHA or pre-flight fails |
| Recording guard | Refuses to apply update if camera is recording |
| `.env` config | All parameters configurable via environment variables |
| `from_env()` | Classmethod builds manager from `NOMON_UPDATE_*` env vars |

### Version Manifest Format

Served by the management server at `NOMON_UPDATE_MANIFEST_URL`:

```json
{
  "version": "0.2.0",
  "git_ref": "v0.2.0",
  "git_sha": "abc123def456...",
  "published_at": "2026-03-01T00:00:00Z",
  "release_notes": "Bug fixes and improvements"
}
```

The `git_sha` field is optional but recommended — when present, HEAD is verified
against it after the pull before any pre-flight or restart.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NOMON_UPDATE_MANIFEST_URL` | *(required)* | URL of JSON version manifest |
| `NOMON_UPDATE_INTERVAL` | `3600.0` | Seconds between manifest checks |
| `NOMON_UPDATE_AUTO_APPLY` | `false` | Auto-apply when update found |
| `NOMON_UPDATE_SYSTEMD_SERVICE` | `nomon` | systemd service name to restart |
| `NOMON_UPDATE_REPO_DIR` | *(auto)* | Git repo root (default: auto-detected) |

### New REST Endpoints

Added to `nomon.api`:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/system/version` | Current version + git hash + UTC timestamp |
| `GET` | `/api/system/update/status` | `update_available`, versions, `last_checked` |
| `POST` | `/api/system/update/apply` | Trigger update; 409 if recording, 503 if no updater or no update available |

---

## Implementation Details

### Source (`src/nomon/updater.py`)

`UpdateManager` public API:

| Method | Description |
|--------|-------------|
| `__init__(...)` | Constructor with full type hints |
| `from_env(camera)` | Classmethod for `.env` config |
| `check_for_update()` | Fetch manifest; returns it if newer, else `None` |
| `apply_update()` | Full update flow with rollback |
| `get_version_info()` | `{version, git_hash, timestamp}` |
| `start_background()` | Start daemon polling thread |
| `stop()` | Signal shutdown |
| `_get_git_hash(repo_dir)` | `git rev-parse HEAD` (static) |
| `_run_preflight(repo_dir)` | Import sanity check subprocess (static) |
| `_apply_git_update(git_ref)` | `git fetch + reset --hard` |
| `_rollback(prev_hash, repo_dir)` | `git reset --hard <hash>` (static) |
| `_restart_service()` | `systemctl restart <service>` |
| `_verify_sha(repo_dir, expected)` | HEAD SHA check (static) |
| `_compute_tree_sha256(repo_dir)` | SHA-256 of `git archive HEAD` (static) |

### Test Coverage (`tests/test_updater.py`)

**48 tests** covering:
- `_parse_version()` — basic parsing, `v` prefix strip, comparison
- Constructor defaults, custom params, invalid interval
- `from_env()` — reads all vars, defaults, raises on missing/empty URL
- `get_version_info()` — keys present, version matches package
- `_get_git_hash()` — success, non-zero rc, exception
- `check_for_update()` — newer available, up-to-date, network error, missing field
- `_run_preflight()` — passes, fails on non-zero rc, fails on exception
- `_verify_sha()` — exact match, prefix match, mismatch, unknown hash
- `apply_update()` — success path, recording guard, no update, missing ref, pre-flight rollback, SHA rollback, git failure
- Thread lifecycle — `start_background()` daemon, `stop()` sets event, `_run_loop` auto-apply
- `UpdateManager` exported from `nomon` package

**New API tests** (`tests/test_api.py`):
- `GET /api/system/version` — version field, matches package
- `GET /api/system/update/status` — no updater, no update, update available
- `POST /api/system/update/apply` — no updater (503), no update (503), success, recording (409), failure (500)

**Test totals: 146 passing (20 camera + 14 streaming + 38 API + 3 integration + 23 telemetry + 48 updater)**

### Code Quality

- ✅ **Black** — Code formatting (line length 100)
- ✅ **Ruff** — Linting (all checks pass)
- ✅ **mypy** — Full static type checking (no issues)
- ✅ **Docstrings** — All public functions and methods documented (NumPy style)
- ✅ **Exception chaining** — `raise ... from` used throughout

---

## Usage

### Basic Setup (Background Polling)

```python
from nomon.updater import UpdateManager

mgr = UpdateManager(manifest_url="https://mgmt.example.com/manifest.json")
thread = mgr.start_background()

# ... application runs ...

mgr.stop()
thread.join()
```

### With Camera (Prevents Update During Recording)

```python
from nomon.camera import Camera
from nomon.updater import UpdateManager

camera = Camera()
mgr = UpdateManager(
    manifest_url="https://mgmt.example.com/manifest.json",
    camera=camera,
)
thread = mgr.start_background()
```

### Auto-Apply Mode

```python
mgr = UpdateManager(
    manifest_url="https://mgmt.example.com/manifest.json",
    auto_apply=True,
    check_interval=3600.0,
)
thread = mgr.start_background()
```

### From `.env`

```dotenv
# .env
NOMON_UPDATE_MANIFEST_URL=https://mgmt.example.com/manifest.json
NOMON_UPDATE_INTERVAL=3600
NOMON_UPDATE_AUTO_APPLY=false
NOMON_UPDATE_SYSTEMD_SERVICE=nomon
```

```python
from dotenv import load_dotenv
from nomon.updater import UpdateManager

load_dotenv()
mgr = UpdateManager.from_env()
thread = mgr.start_background()
```

### One-Shot Check & Manual Apply

```python
mgr = UpdateManager(manifest_url="https://mgmt.example.com/manifest.json")
manifest = mgr.check_for_update()
if manifest:
    print(f"Update available: {manifest['version']}")
    mgr.apply_update()
```

---

## Architecture Decisions

### Why stdlib only (no `requests`/`httpx`)?

The project philosophy keeps the core dependency list minimal.  `urllib.request`
from the standard library handles the simple manifest fetch (single GET with a
15-second timeout).  No authentication or streaming is needed.

### Why `git reset --hard` instead of `git pull`?

`git pull` can fail on merge conflicts or detached HEADs.  `git fetch --tags origin`
followed by `git reset --hard <ref>` is deterministic — it always reaches the
exact target state regardless of local modifications or history divergence.

### Why pre-flight only (no post-restart rollback)?

Once `systemctl restart` is issued, the current process is terminated.  Post-restart
rollback detection (observing systemd service status from within the new process)
adds significant complexity for limited benefit.  The pre-flight check — running
`python -c "import nomon"` before the restart — catches the most common failure mode
(import errors from broken code) at negligible cost.

---

## What's Next

### Phase 5 — HAT Module Driver

- Standalone Rust `nomon-hat` daemon in a separate repository (see ADR-006)
- Local integration between `nomon` and `nomon-hat` (daemon process manages all HAT I/O)
- REST endpoints under `/api/hat/...` in `nomon.api` acting as a thin adapter to the daemon
