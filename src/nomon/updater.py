"""OTA update manager for nomon fleet devices.

This module provides a background polling loop that checks a remote version
manifest for newer releases and can apply updates via ``git pull`` + systemd
restart.  A pre-flight import check guards against broken updates; if it fails
the local repository is rolled back before any restart is attempted.

Classes
-------
UpdateManager
    Polls a manifest URL, detects available updates, and applies them safely.
"""

import hashlib
import json
import logging
import os
import subprocess
import sys
import threading
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_DEFAULT_INTERVAL: float = 3600.0
_DEFAULT_SERVICE: str = "nomon"


def _detect_repo_dir() -> Path:
    """Return the root of the nomon git repository.

    Walks up from the location of this source file until a ``.git`` directory
    is found, or returns the package parent as a best-guess fallback.

    Returns
    -------
    Path
        Absolute path to the repository root.
    """
    candidate = Path(__file__).resolve().parent
    for _ in range(6):
        if (candidate / ".git").is_dir():
            return candidate
        candidate = candidate.parent
    # Fallback: two levels above this file (src/nomon → project root)
    return Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Version comparison helper
# ---------------------------------------------------------------------------


def _parse_version(version_str: str) -> tuple[int, ...]:
    """Parse a ``MAJOR.MINOR.PATCH`` version string into a comparable tuple.

    Parameters
    ----------
    version_str : str
        Version string such as ``"0.2.0"`` or ``"1.0.0"``.

    Returns
    -------
    tuple[int, ...]
        Integer tuple, e.g. ``(0, 2, 0)``.  Non-numeric parts are treated
        as ``0``.
    """
    parts = []
    for part in version_str.strip().lstrip("v").split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return tuple(parts)


# ---------------------------------------------------------------------------
# UpdateManager
# ---------------------------------------------------------------------------


class UpdateManager:
    """Polls a version manifest and applies OTA updates to a nomon device.

    The manager runs as a daemon background thread.  On each check it fetches
    a JSON manifest from ``manifest_url``, compares the advertised version
    against the currently installed version, and (when ``auto_apply`` is
    ``True``) applies the update.

    Update procedure
    ----------------
    1. Record the current git HEAD hash as a rollback point.
    2. ``git fetch origin && git reset --hard <git_sha_or_ref>``.
    3. Verify HEAD SHA matches ``manifest["git_sha"]`` (when present).
    4. Run a pre-flight import check (``python -c "import nomon"``).
    5. If pre-flight **passes**: ``systemctl restart <service>``.
    6. If pre-flight **fails**: ``git reset --hard <rollback_hash>`` then raise.

    Parameters
    ----------
    manifest_url : str
        URL that returns a JSON version manifest.
    check_interval : float, optional
        Seconds between manifest checks (default: 3600).
    camera : Camera, optional
        Live camera instance; update is refused if the camera is recording.
    auto_apply : bool, optional
        Automatically apply updates when found (default: ``False``).
    systemd_service : str, optional
        Name of the systemd service to restart (default: ``"nomon"``).
    repo_dir : Path, optional
        Root of the git repository (default: auto-detected).

    Raises
    ------
    ValueError
        If ``check_interval`` is not positive.

    Examples
    --------
    >>> mgr = UpdateManager(manifest_url="https://mgmt.example.com/manifest.json")
    >>> thread = mgr.start_background()
    >>> # ...
    >>> mgr.stop()
    >>> thread.join()
    """

    def __init__(
        self,
        manifest_url: str,
        check_interval: float = _DEFAULT_INTERVAL,
        camera: Optional[Any] = None,
        auto_apply: bool = False,
        systemd_service: str = _DEFAULT_SERVICE,
        repo_dir: Optional[Path] = None,
    ) -> None:
        if check_interval <= 0:
            raise ValueError(f"check_interval must be positive, got {check_interval}")

        self.manifest_url = manifest_url
        self.check_interval = check_interval
        self.camera = camera
        self.auto_apply = auto_apply
        self.systemd_service = systemd_service
        self.repo_dir: Path = repo_dir or _detect_repo_dir()

        # Mutable state — protected by _lock
        self._lock = threading.Lock()
        self.update_available: bool = False
        self.latest_manifest: Optional[dict[str, Any]] = None
        self.last_checked: Optional[datetime] = None

        self._stop_event = threading.Event()

    # -------------------------------------------------------------------------
    # Construction helpers
    # -------------------------------------------------------------------------

    @classmethod
    def from_env(cls, camera: Optional[Any] = None) -> "UpdateManager":
        """Create an ``UpdateManager`` from environment variables.

        Environment variables
        ---------------------
        NOMON_UPDATE_MANIFEST_URL : str
            URL of the version manifest (required).
        NOMON_UPDATE_INTERVAL : float
            Seconds between manifest checks (default: ``3600.0``).
        NOMON_UPDATE_AUTO_APPLY : str
            ``"true"`` to enable automatic update application (default: ``"false"``).
        NOMON_UPDATE_SYSTEMD_SERVICE : str
            systemd service name (default: ``"nomon"``).
        NOMON_UPDATE_REPO_DIR : str
            Absolute path to the git repository root (default: auto-detected).

        Parameters
        ----------
        camera : Camera, optional
            Live camera instance to check recording state before applying.

        Returns
        -------
        UpdateManager
            Configured manager instance.

        Raises
        ------
        ValueError
            If ``NOMON_UPDATE_MANIFEST_URL`` is not set.
        """
        manifest_url = os.environ.get("NOMON_UPDATE_MANIFEST_URL", "").strip()
        if not manifest_url:
            raise ValueError("NOMON_UPDATE_MANIFEST_URL environment variable is required.")

        check_interval = float(os.environ.get("NOMON_UPDATE_INTERVAL", str(_DEFAULT_INTERVAL)))
        auto_apply = os.environ.get("NOMON_UPDATE_AUTO_APPLY", "false").strip().lower() == "true"
        systemd_service = os.environ.get("NOMON_UPDATE_SYSTEMD_SERVICE", _DEFAULT_SERVICE).strip()
        repo_dir_str = os.environ.get("NOMON_UPDATE_REPO_DIR", "").strip()
        repo_dir = Path(repo_dir_str) if repo_dir_str else None

        return cls(
            manifest_url=manifest_url,
            check_interval=check_interval,
            camera=camera,
            auto_apply=auto_apply,
            systemd_service=systemd_service,
            repo_dir=repo_dir,
        )

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def get_version_info(self) -> dict[str, Any]:
        """Return the current installed version and git hash.

        Returns
        -------
        dict[str, Any]
            Dictionary with keys ``"version"`` (str), ``"git_hash"`` (str),
            and ``"timestamp"`` (ISO 8601 UTC str).  ``"git_hash"`` is
            ``"unknown"`` if the git command fails.
        """
        from nomon import __version__

        return {
            "version": __version__,
            "git_hash": self._get_git_hash(self.repo_dir),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def check_for_update(self) -> Optional[dict[str, Any]]:
        """Fetch the manifest and return it if a newer version is available.

        Compares ``manifest["version"]`` against the currently installed
        ``nomon.__version__``.  Updates ``update_available``, ``latest_manifest``,
        and ``last_checked`` under the instance lock.

        Returns
        -------
        dict[str, Any] or None
            The manifest dict when a newer version is available, ``None``
            when already up-to-date or if the fetch/parse fails.
        """
        from nomon import __version__

        try:
            manifest = self._fetch_manifest()
        except Exception as exc:
            logger.warning("Failed to fetch update manifest from %s: %s", self.manifest_url, exc)
            with self._lock:
                self.last_checked = datetime.now(timezone.utc)
            return None

        manifest_version = manifest.get("version", "")
        if not manifest_version:
            logger.warning("Manifest missing 'version' field.")
            with self._lock:
                self.last_checked = datetime.now(timezone.utc)
            return None

        try:
            newer = _parse_version(manifest_version) > _parse_version(__version__)
        except Exception as exc:
            logger.warning("Version comparison failed: %s", exc)
            newer = False

        with self._lock:
            self.update_available = newer
            self.latest_manifest = manifest
            self.last_checked = datetime.now(timezone.utc)

        if newer:
            logger.info("Update available: %s → %s", __version__, manifest_version)
        else:
            logger.debug("Already up to date (%s).", __version__)

        return manifest if newer else None

    def apply_update(self) -> bool:
        """Apply the latest available update.

        Procedure
        ---------
        1. Refuse if camera is currently recording.
        2. Refuse if no update is available (``update_available`` is ``False``).
        3. Record rollback hash.
        4. ``git fetch`` + ``git reset --hard`` to the manifest's ref/SHA.
        5. Verify HEAD SHA against manifest ``"git_sha"`` (when present).
        6. Run pre-flight import check.
        7. If pre-flight passes: restart systemd service.
        8. If pre-flight fails or SHA mismatch: roll back, then raise.

        Returns
        -------
        bool
            ``True`` on success (service restart triggered).

        Raises
        ------
        RuntimeError
            If the camera is recording, no update is available, the git
            operation fails, SHA verification fails, or pre-flight fails.
        """
        # --- Guard: recording in progress ---
        if self.camera is not None:
            try:
                if self.camera._is_recording:
                    raise RuntimeError("Cannot apply update while camera is recording.")
            except AttributeError:
                pass

        # --- Guard: no update queued ---
        with self._lock:
            if not self.update_available or self.latest_manifest is None:
                raise RuntimeError("No update available. Call check_for_update() first.")
            manifest = dict(self.latest_manifest)

        git_ref = manifest.get("git_sha") or manifest.get("git_ref") or ""
        if not git_ref:
            raise RuntimeError("Manifest does not contain 'git_sha' or 'git_ref'.")

        expected_sha = manifest.get("git_sha", "")

        # --- Record rollback point ---
        prev_hash = self._get_git_hash(self.repo_dir)
        if prev_hash == "unknown":
            logger.error("Cannot apply update: unable to determine current git hash for rollback.")
            raise RuntimeError("Cannot apply update without a valid rollback point.")
        logger.info("Applying update to %s (rollback point: %s)", git_ref, prev_hash)

        # --- Pull ---
        try:
            self._apply_git_update(git_ref)
        except Exception as exc:
            raise RuntimeError(f"git update to {git_ref!r} failed: {exc}") from exc

        # --- SHA verification ---
        if expected_sha:
            if not self._verify_sha(self.repo_dir, expected_sha):
                logger.error("SHA mismatch after update (expected %s). Rolling back.", expected_sha)
                self._rollback(prev_hash, self.repo_dir)
                raise RuntimeError(
                    f"SHA verification failed: expected {expected_sha!r}. Rolled back."
                )

        # --- Pre-flight ---
        if not self._run_preflight(self.repo_dir):
            logger.error("Pre-flight check failed after update. Rolling back.")
            self._rollback(prev_hash, self.repo_dir)
            raise RuntimeError("Pre-flight import check failed after update. Rolled back.")

        # --- Restart ---
        logger.info("Pre-flight passed. Restarting service '%s'.", self.systemd_service)
        self._restart_service()

        with self._lock:
            self.update_available = False

        return True

    def start_background(self) -> threading.Thread:
        """Start the update polling loop in a daemon background thread.

        Returns
        -------
        threading.Thread
            The daemon thread running the polling loop.
        """
        self._stop_event.clear()
        thread = threading.Thread(target=self._run_loop, name="nomon-updater", daemon=True)
        thread.start()
        logger.info(
            "Update manager started (manifest=%s interval=%.0fs auto_apply=%s)",
            self.manifest_url,
            self.check_interval,
            self.auto_apply,
        )
        return thread

    def stop(self) -> None:
        """Signal the polling loop to stop.

        Sets the internal stop event; the background thread exits after the
        current sleep interval.  Call ``thread.join()`` after this for a
        clean shutdown.
        """
        self._stop_event.set()
        logger.info("Update manager stop requested.")

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _fetch_manifest(self) -> dict[str, Any]:
        """Fetch and parse the version manifest JSON.

        Returns
        -------
        dict[str, Any]
            Parsed manifest.

        Raises
        ------
        RuntimeError
            If the HTTP request fails or the response is not valid JSON.
        """
        try:
            with urllib.request.urlopen(self.manifest_url, timeout=15) as response:
                raw = response.read()
        except Exception as exc:
            raise RuntimeError(f"HTTP request to {self.manifest_url!r} failed: {exc}") from exc

        try:
            return json.loads(raw)  # type: ignore[no-any-return]
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Manifest from {self.manifest_url!r} is not valid JSON: {exc}"
            ) from exc

    @staticmethod
    def _get_git_hash(repo_dir: Path) -> str:
        """Return the current git HEAD commit hash.

        Parameters
        ----------
        repo_dir : Path
            Root of the git repository.

        Returns
        -------
        str
            Full 40-character SHA-1 hash, or ``"unknown"`` on failure.
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(repo_dir),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as exc:
            logger.debug("Could not determine git hash: %s", exc)
        return "unknown"

    @staticmethod
    def _run_preflight(repo_dir: Path) -> bool:
        """Run a basic import sanity check on the updated code.

        Executes ``python -c "import nomon"`` in a fresh subprocess so that
        import errors in the updated code are detected before the service is
        restarted.

        Parameters
        ----------
        repo_dir : Path
            Root of the git repository (used to set ``PYTHONPATH``).

        Returns
        -------
        bool
            ``True`` if the import succeeds, ``False`` otherwise.
        """
        src_dir = str(repo_dir / "src")
        env = os.environ.copy()
        existing_path = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{existing_path}" if existing_path else src_dir

        try:
            result = subprocess.run(
                [sys.executable, "-c", "import nomon"],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning(
                    "Pre-flight import check failed (rc=%d): %s",
                    result.returncode,
                    result.stderr.strip(),
                )
                return False
            return True
        except Exception as exc:
            logger.warning("Pre-flight check raised an exception: %s", exc)
            return False

    def _apply_git_update(self, git_ref: str) -> None:
        """Fetch from origin and reset HEAD to the given ref or SHA.

        Parameters
        ----------
        git_ref : str
            A git tag, branch name, or full commit SHA to reset to.

        Raises
        ------
        RuntimeError
            If either git command exits with a non-zero return code.
        """
        fetch_result = subprocess.run(
            ["git", "fetch", "--tags", "origin"],
            cwd=str(self.repo_dir),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if fetch_result.returncode != 0:
            raise RuntimeError(
                f"git fetch failed (rc={fetch_result.returncode}): {fetch_result.stderr.strip()}"
            )

        reset_result = subprocess.run(
            ["git", "reset", "--hard", git_ref],
            cwd=str(self.repo_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if reset_result.returncode != 0:
            raise RuntimeError(
                f"git reset --hard {git_ref!r} failed "
                f"(rc={reset_result.returncode}): {reset_result.stderr.strip()}"
            )

        logger.info("git reset --hard %s succeeded.", git_ref)

    @staticmethod
    def _rollback(prev_hash: str, repo_dir: Path) -> None:
        """Roll back the repository to a previous commit hash.

        Parameters
        ----------
        prev_hash : str
            Full git commit SHA to reset to.
        repo_dir : Path
            Root of the git repository.
        """
        if prev_hash == "unknown":
            logger.error("Cannot rollback: previous hash is 'unknown'.")
            return

        try:
            result = subprocess.run(
                ["git", "reset", "--hard", prev_hash],
                cwd=str(repo_dir),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info("Rolled back to %s.", prev_hash)
            else:
                logger.error(
                    "Rollback to %s failed (rc=%d): %s",
                    prev_hash,
                    result.returncode,
                    result.stderr.strip(),
                )
        except Exception as exc:
            logger.error("Rollback raised an exception: %s", exc)

    def _restart_service(self) -> None:
        """Restart the nomon systemd service.

        Raises
        ------
        RuntimeError
            If ``systemctl restart`` exits with a non-zero return code.
        """
        result = subprocess.run(
            ["systemctl", "restart", self.systemd_service],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"systemctl restart {self.systemd_service!r} failed "
                f"(rc={result.returncode}): {result.stderr.strip()}"
            )
        logger.info("systemctl restart %s succeeded.", self.systemd_service)

    @staticmethod
    def _verify_sha(repo_dir: Path, expected_sha: str) -> bool:
        """Verify the current HEAD SHA matches the expected value.

        A full-length git SHA-1 string is compared directly.  Shortened
        (prefix) SHAs are supported via a ``startswith`` check.

        Parameters
        ----------
        repo_dir : Path
            Root of the git repository.
        expected_sha : str
            Full or prefix SHA expected after the update.

        Returns
        -------
        bool
            ``True`` if the HEAD SHA matches, ``False`` otherwise.
        """
        current = UpdateManager._get_git_hash(repo_dir)
        if current == "unknown":
            logger.warning("Cannot verify SHA: git hash is 'unknown'.")
            return False

        # Accept both full SHA and shortened prefix
        match = current == expected_sha or current.startswith(expected_sha)
        if not match:
            logger.warning("SHA mismatch: HEAD is %s, expected %s.", current, expected_sha)
        return match

    @staticmethod
    def _compute_tree_sha256(repo_dir: Path) -> str:
        """Compute a SHA-256 digest of the git-tracked file tree.

        Uses ``git archive HEAD`` piped through ``hashlib.sha256`` to produce
        a deterministic digest of the current working tree as tracked by git.
        This is suitable for verifying a downloaded release against a manifest
        ``sha256`` field.

        Parameters
        ----------
        repo_dir : Path
            Root of the git repository.

        Returns
        -------
        str
            Hexadecimal SHA-256 digest string, or ``"unknown"`` on failure.
        """
        try:
            proc = subprocess.Popen(
                ["git", "archive", "HEAD"],
                cwd=str(repo_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            sha = hashlib.sha256()
            assert proc.stdout is not None
            while chunk := proc.stdout.read(65536):
                sha.update(chunk)
            proc.wait(timeout=30)
            if proc.returncode != 0:
                return "unknown"
            return sha.hexdigest()
        except Exception as exc:
            logger.debug("Could not compute tree SHA-256: %s", exc)
            return "unknown"

    def _run_loop(self) -> None:
        """Background thread: poll manifest periodically and optionally apply."""
        while not self._stop_event.is_set():
            manifest = self.check_for_update()

            if manifest and self.auto_apply:
                logger.info("Auto-applying update to version %s.", manifest.get("version"))
                try:
                    self.apply_update()
                except RuntimeError as exc:
                    logger.error("Auto-apply failed: %s", exc)

            self._stop_event.wait(timeout=self.check_interval)

        logger.info("Update manager stopped.")
