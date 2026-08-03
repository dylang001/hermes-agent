"""Tests for the update check mechanism in hermes_cli.banner."""

import json
import os
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest




def test_check_for_updates_uses_cache(tmp_path, monkeypatch):
    """When cache is fresh, check_for_updates should return cached value without calling git."""
    from hermes_cli.banner import check_for_updates
    from hermes_cli import __version__

    # Create a fake git repo and fresh cache
    repo_dir = tmp_path / "hermes-agent"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()

    cache_file = tmp_path / ".update_check"
    cache_file.write_text(json.dumps({"ts": time.time(), "behind": 3, "ver": __version__}))

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    with patch("hermes_cli.banner.subprocess.run") as mock_run:
        result = check_for_updates()

    assert result == 3
    mock_run.assert_not_called()






def test_prefetch_non_blocking():
    """prefetch_update_check() should return immediately without blocking."""
    import hermes_cli.banner as banner

    # Reset module state
    banner._update_result = None
    banner._update_check_done = threading.Event()

    with patch.object(banner, "check_for_updates", return_value=5):
        start = time.monotonic()
        banner.prefetch_update_check()
        elapsed = time.monotonic() - start

        # Should return almost immediately (well under 1 second)
        assert elapsed < 1.0

        # Wait for the background thread to finish
        banner._update_check_done.wait(timeout=5)
        assert banner._update_result == 5


def test_bundle_origin_uses_private_official_upstream_ref(tmp_path):
    """A deployment bundle must not make carried commits look unprotected."""
    import hermes_cli.banner as banner

    repo_dir = tmp_path / "hermes-agent"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()

    def fake_run(cmd, **kwargs):
        if cmd == ["git", "remote", "get-url", "origin"]:
            return MagicMock(returncode=0, stdout="/opt/hermes/deploy/runtime.bundle\n")
        if cmd[:4] == ["git", "fetch", "--quiet", banner._UPSTREAM_REPO_URL]:
            return MagicMock(returncode=0, stdout="")
        if cmd == ["git", "rev-parse", "HEAD"]:
            return MagicMock(returncode=0, stdout="local-sha\n")
        if cmd == ["git", "rev-parse", banner._HERMES_UPSTREAM_REF]:
            return MagicMock(returncode=0, stdout="upstream-sha\n")
        if cmd == ["git", "rev-list", "--count", f"HEAD..{banner._HERMES_UPSTREAM_REF}"]:
            return MagicMock(returncode=0, stdout="0\n")
        if cmd == ["git", "rev-list", "--count", f"{banner._HERMES_UPSTREAM_REF}..HEAD"]:
            return MagicMock(returncode=0, stdout="107\n")
        raise AssertionError(f"unexpected git command: {cmd!r}")

    with patch("hermes_cli.banner.subprocess.run", side_effect=fake_run):
        assert banner._check_via_local_git(repo_dir) == 0
        status = banner.get_upstream_sync_status(repo_dir)

    assert status["behind"] == 0
    assert status["ahead"] == 107
    assert status["upstream_ref"] == banner._HERMES_UPSTREAM_REF



