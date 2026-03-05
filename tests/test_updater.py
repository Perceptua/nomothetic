"""Tests for the OTA update manager module.

All git, subprocess, and HTTP calls are mocked so that tests run on
non-Pi, non-Linux systems without any real git repository or network.
"""

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nomon.updater import UpdateManager, _parse_version

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manager(**kwargs) -> UpdateManager:
    """Return an UpdateManager with sensible test defaults."""
    defaults = {
        "manifest_url": "https://mgmt.example.com/manifest.json",
        "check_interval": 3600.0,
        "repo_dir": Path("/fake/repo"),
    }
    defaults.update(kwargs)
    return UpdateManager(**defaults)


def _manifest(version: str = "0.2.0", git_sha: str = "abc123") -> dict:
    return {
        "version": version,
        "git_ref": f"v{version}",
        "git_sha": git_sha,
        "published_at": "2026-03-01T00:00:00Z",
        "release_notes": "Test release",
    }


# ---------------------------------------------------------------------------
# _parse_version
# ---------------------------------------------------------------------------


def test_parse_version_basic():
    assert _parse_version("0.1.0") == (0, 1, 0)
    assert _parse_version("1.2.3") == (1, 2, 3)


def test_parse_version_strips_v_prefix():
    assert _parse_version("v0.2.0") == (0, 2, 0)


def test_parse_version_comparison():
    assert _parse_version("0.2.0") > _parse_version("0.1.0")
    assert _parse_version("1.0.0") > _parse_version("0.9.9")
    assert _parse_version("0.1.0") == _parse_version("0.1.0")


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


def test_constructor_defaults():
    mgr = _make_manager()
    assert mgr.manifest_url == "https://mgmt.example.com/manifest.json"
    assert mgr.check_interval == 3600.0
    assert mgr.auto_apply is False
    assert mgr.systemd_service == "nomon"
    assert mgr.update_available is False
    assert mgr.latest_manifest is None
    assert mgr.last_checked is None
    assert mgr.camera is None


def test_constructor_custom_params():
    mgr = _make_manager(
        check_interval=600.0,
        auto_apply=True,
        systemd_service="my-service",
    )
    assert mgr.check_interval == 600.0
    assert mgr.auto_apply is True
    assert mgr.systemd_service == "my-service"


def test_constructor_rejects_non_positive_interval():
    with pytest.raises(ValueError, match="check_interval must be positive"):
        _make_manager(check_interval=0)

    with pytest.raises(ValueError, match="check_interval must be positive"):
        _make_manager(check_interval=-1.0)


# ---------------------------------------------------------------------------
# from_env
# ---------------------------------------------------------------------------


def test_from_env_reads_all_vars(monkeypatch):
    monkeypatch.setenv("NOMON_UPDATE_MANIFEST_URL", "https://example.com/manifest.json")
    monkeypatch.setenv("NOMON_UPDATE_INTERVAL", "600")
    monkeypatch.setenv("NOMON_UPDATE_AUTO_APPLY", "true")
    monkeypatch.setenv("NOMON_UPDATE_SYSTEMD_SERVICE", "my-nomon")
    monkeypatch.setenv("NOMON_UPDATE_REPO_DIR", "/tmp/repo")

    mgr = UpdateManager.from_env()

    assert mgr.manifest_url == "https://example.com/manifest.json"
    assert mgr.check_interval == 600.0
    assert mgr.auto_apply is True
    assert mgr.systemd_service == "my-nomon"
    assert mgr.repo_dir == Path("/tmp/repo")


def test_from_env_defaults(monkeypatch):
    monkeypatch.setenv("NOMON_UPDATE_MANIFEST_URL", "https://example.com/manifest.json")
    for var in [
        "NOMON_UPDATE_INTERVAL",
        "NOMON_UPDATE_AUTO_APPLY",
        "NOMON_UPDATE_SYSTEMD_SERVICE",
        "NOMON_UPDATE_REPO_DIR",
    ]:
        monkeypatch.delenv(var, raising=False)

    mgr = UpdateManager.from_env()

    assert mgr.check_interval == 3600.0
    assert mgr.auto_apply is False
    assert mgr.systemd_service == "nomon"


def test_from_env_raises_without_manifest_url(monkeypatch):
    monkeypatch.delenv("NOMON_UPDATE_MANIFEST_URL", raising=False)
    with pytest.raises(ValueError, match="NOMON_UPDATE_MANIFEST_URL"):
        UpdateManager.from_env()


def test_from_env_raises_on_empty_manifest_url(monkeypatch):
    monkeypatch.setenv("NOMON_UPDATE_MANIFEST_URL", "   ")
    with pytest.raises(ValueError, match="NOMON_UPDATE_MANIFEST_URL"):
        UpdateManager.from_env()


# ---------------------------------------------------------------------------
# get_version_info
# ---------------------------------------------------------------------------


def test_get_version_info_contains_expected_keys():
    mgr = _make_manager()
    with patch.object(UpdateManager, "_get_git_hash", return_value="deadbeef"):
        info = mgr.get_version_info()

    assert "version" in info
    assert "git_hash" in info
    assert "timestamp" in info
    assert info["git_hash"] == "deadbeef"


def test_get_version_info_version_matches_package():
    import nomon

    mgr = _make_manager()
    with patch.object(UpdateManager, "_get_git_hash", return_value="abc"):
        info = mgr.get_version_info()

    assert info["version"] == nomon.__version__


# ---------------------------------------------------------------------------
# _get_git_hash
# ---------------------------------------------------------------------------


def test_get_git_hash_success():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "abc123def456\n"

    with patch("nomon.updater.subprocess.run", return_value=mock_result):
        result = UpdateManager._get_git_hash(Path("/fake/repo"))

    assert result == "abc123def456"


def test_get_git_hash_failure_returns_unknown():
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""

    with patch("nomon.updater.subprocess.run", return_value=mock_result):
        result = UpdateManager._get_git_hash(Path("/fake/repo"))

    assert result == "unknown"


def test_get_git_hash_exception_returns_unknown():
    with patch("nomon.updater.subprocess.run", side_effect=OSError("no git")):
        result = UpdateManager._get_git_hash(Path("/fake/repo"))

    assert result == "unknown"


# ---------------------------------------------------------------------------
# check_for_update
# ---------------------------------------------------------------------------


def test_check_for_update_returns_manifest_when_newer():
    mgr = _make_manager()
    manifest = _manifest(version="99.0.0", git_sha="newsha")

    with patch.object(mgr, "_fetch_manifest", return_value=manifest):
        result = mgr.check_for_update()

    assert result is not None
    assert result["version"] == "99.0.0"
    assert mgr.update_available is True
    assert mgr.latest_manifest == manifest
    assert mgr.last_checked is not None


def test_check_for_update_returns_none_when_up_to_date():
    mgr = _make_manager()
    manifest = _manifest(version="0.0.1")  # older than the patched current version

    with patch("nomon.__version__", "1.0.0"), patch.object(
        mgr, "_fetch_manifest", return_value=manifest
    ):
        result = mgr.check_for_update()

    assert result is None
    assert mgr.update_available is False
    assert mgr.last_checked is not None


def test_check_for_update_handles_network_error():
    mgr = _make_manager()

    with patch.object(mgr, "_fetch_manifest", side_effect=RuntimeError("timeout")):
        result = mgr.check_for_update()

    assert result is None
    assert mgr.update_available is False
    assert mgr.last_checked is not None


def test_check_for_update_handles_missing_version_field():
    mgr = _make_manager()

    with patch.object(mgr, "_fetch_manifest", return_value={"release_notes": "bad manifest"}):
        result = mgr.check_for_update()

    assert result is None


# ---------------------------------------------------------------------------
# _run_preflight
# ---------------------------------------------------------------------------


def test_run_preflight_passes():
    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("nomon.updater.subprocess.run", return_value=mock_result):
        assert UpdateManager._run_preflight(Path("/fake/repo")) is True


def test_run_preflight_fails_on_nonzero_rc():
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "ImportError: no module named nomon"

    with patch("nomon.updater.subprocess.run", return_value=mock_result):
        assert UpdateManager._run_preflight(Path("/fake/repo")) is False


def test_run_preflight_fails_on_exception():
    with patch("nomon.updater.subprocess.run", side_effect=OSError("no python")):
        assert UpdateManager._run_preflight(Path("/fake/repo")) is False


# ---------------------------------------------------------------------------
# _verify_sha
# ---------------------------------------------------------------------------


def test_verify_sha_exact_match():
    with patch.object(UpdateManager, "_get_git_hash", return_value="abc123"):
        assert UpdateManager._verify_sha(Path("/fake"), "abc123") is True


def test_verify_sha_prefix_match():
    with patch.object(UpdateManager, "_get_git_hash", return_value="abc123def456"):
        assert UpdateManager._verify_sha(Path("/fake"), "abc123") is True


def test_verify_sha_mismatch():
    with patch.object(UpdateManager, "_get_git_hash", return_value="abc123"):
        assert UpdateManager._verify_sha(Path("/fake"), "xyz999") is False


def test_verify_sha_unknown_hash():
    with patch.object(UpdateManager, "_get_git_hash", return_value="unknown"):
        assert UpdateManager._verify_sha(Path("/fake"), "abc123") is False


# ---------------------------------------------------------------------------
# apply_update — success path
# ---------------------------------------------------------------------------


def test_apply_update_success():
    mgr = _make_manager()
    manifest = _manifest(version="99.0.0", git_sha="newsha456")

    # Seed state as if check_for_update already ran
    mgr.update_available = True
    mgr.latest_manifest = manifest

    with (
        patch.object(UpdateManager, "_get_git_hash", return_value="oldsha"),
        patch.object(mgr, "_apply_git_update") as mock_apply,
        patch.object(UpdateManager, "_verify_sha", return_value=True),
        patch.object(UpdateManager, "_run_preflight", return_value=True),
        patch.object(mgr, "_restart_service") as mock_restart,
    ):
        result = mgr.apply_update()

    assert result is True
    mock_apply.assert_called_once_with("newsha456")
    mock_restart.assert_called_once()
    assert mgr.update_available is False


# ---------------------------------------------------------------------------
# apply_update — failure paths
# ---------------------------------------------------------------------------


def test_apply_update_aborts_when_recording():
    mgr = _make_manager()
    mgr.update_available = True
    mgr.latest_manifest = _manifest()

    mock_camera = MagicMock()
    mock_camera._is_recording = True
    mgr.camera = mock_camera

    with pytest.raises(RuntimeError, match="recording"):
        mgr.apply_update()


def test_apply_update_raises_when_no_update_available():
    mgr = _make_manager()
    mgr.update_available = False

    with pytest.raises(RuntimeError, match="No update available"):
        mgr.apply_update()


def test_apply_update_raises_on_missing_ref_in_manifest():
    mgr = _make_manager()
    mgr.update_available = True
    mgr.latest_manifest = {"version": "0.2.0"}  # no git_sha or git_ref

    with pytest.raises(RuntimeError, match="git_sha.*git_ref"):
        mgr.apply_update()


def test_apply_update_aborts_when_rollback_point_unknown():
    mgr = _make_manager()
    mgr.update_available = True
    mgr.latest_manifest = _manifest(git_sha="newsha")

    with (
        patch.object(UpdateManager, "_get_git_hash", return_value="unknown"),
    ):
        with pytest.raises(RuntimeError, match="rollback point"):
            mgr.apply_update()


def test_apply_update_rolls_back_on_preflight_failure():
    mgr = _make_manager()
    mgr.update_available = True
    mgr.latest_manifest = _manifest(git_sha="newsha")

    rollback_calls = []

    with (
        patch.object(UpdateManager, "_get_git_hash", return_value="oldsha"),
        patch.object(mgr, "_apply_git_update"),
        patch.object(UpdateManager, "_verify_sha", return_value=True),
        patch.object(UpdateManager, "_run_preflight", return_value=False),
        patch.object(UpdateManager, "_rollback", side_effect=lambda h, d: rollback_calls.append(h)),
    ):
        with pytest.raises(RuntimeError, match="Pre-flight"):
            mgr.apply_update()

    assert "oldsha" in rollback_calls


def test_apply_update_rolls_back_on_sha_mismatch():
    mgr = _make_manager()
    mgr.update_available = True
    mgr.latest_manifest = _manifest(git_sha="expected_sha")

    rollback_calls = []

    with (
        patch.object(UpdateManager, "_get_git_hash", return_value="oldsha"),
        patch.object(mgr, "_apply_git_update"),
        patch.object(UpdateManager, "_verify_sha", return_value=False),
        patch.object(UpdateManager, "_rollback", side_effect=lambda h, d: rollback_calls.append(h)),
    ):
        with pytest.raises(RuntimeError, match="SHA verification"):
            mgr.apply_update()

    assert "oldsha" in rollback_calls


def test_apply_update_raises_on_git_pull_failure():
    mgr = _make_manager()
    mgr.update_available = True
    mgr.latest_manifest = _manifest()

    with (
        patch.object(UpdateManager, "_get_git_hash", return_value="oldsha"),
        patch.object(mgr, "_apply_git_update", side_effect=RuntimeError("git fetch failed")),
    ):
        with pytest.raises(RuntimeError, match="git update"):
            mgr.apply_update()


# ---------------------------------------------------------------------------
# Background thread lifecycle
# ---------------------------------------------------------------------------


def test_start_background_returns_daemon_thread():
    mgr = _make_manager()

    with patch.object(mgr, "_run_loop"):
        thread = mgr.start_background()

    assert isinstance(thread, threading.Thread)
    assert thread.daemon is True
    mgr.stop()
    thread.join(timeout=1)


def test_stop_sets_stop_event():
    mgr = _make_manager()
    assert not mgr._stop_event.is_set()
    mgr.stop()
    assert mgr._stop_event.is_set()


def test_run_loop_calls_check_and_apply_when_auto_apply():
    """With auto_apply=True the loop should call apply_update when update found."""
    mgr = _make_manager(auto_apply=True, check_interval=0.001)
    manifest = _manifest(version="99.0.0")
    check_count = {"n": 0}

    def fake_check():
        check_count["n"] += 1
        if check_count["n"] == 1:
            mgr.update_available = True
            mgr.latest_manifest = manifest
            return manifest
        mgr._stop_event.set()
        return None

    with (
        patch.object(mgr, "check_for_update", side_effect=fake_check),
        patch.object(mgr, "apply_update") as mock_apply,
    ):
        mgr._run_loop()

    mock_apply.assert_called_once()


# ---------------------------------------------------------------------------
# Package-level export
# ---------------------------------------------------------------------------


def test_update_manager_exported_from_nomon():
    import nomon

    assert hasattr(nomon, "UpdateManager")
    assert nomon.UpdateManager is UpdateManager
