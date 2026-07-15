"""Path-boundary guards: never walk /root/.git on /opt/hermes deployments."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.path_boundary import (
    is_blocked_legacy_path,
    path_is_usable_dir,
    preferred_fallback_cwd,
    remap_stale_path_text,
    sanitize_cwd,
)
from agent.prompt_builder import _find_git_root, build_context_files_prompt
from agent.runtime_cwd import resolve_agent_cwd, set_session_cwd
from agent.runtime_metadata import remap_stale_paths


def test_blocked_legacy_paths_include_root_and_git():
    assert is_blocked_legacy_path("/root")
    assert is_blocked_legacy_path("/root/.git")
    assert is_blocked_legacy_path("/root/audit/notes.md")
    assert is_blocked_legacy_path("/usr/local/lib/hermes-agent")
    assert not is_blocked_legacy_path("/opt/hermes/app")
    assert not is_blocked_legacy_path("/opt/hermes/home")


def test_sanitize_cwd_resets_stale_root(monkeypatch, tmp_path):
    app = tmp_path / "opt" / "hermes" / "app"
    app.mkdir(parents=True)
    (app / "run_agent.py").write_text("#\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_APP_ROOT", str(app))
    monkeypatch.setenv("TERMINAL_ENV", "local")
    monkeypatch.delenv("TERMINAL_CWD", raising=False)

    assert sanitize_cwd("/root") == str(app.resolve())
    assert sanitize_cwd("/root/.git") == str(app.resolve())


def test_find_git_root_skips_inaccessible_root(monkeypatch, tmp_path):
    """Simulate session cwd=/root without requiring a real /root/.git probe crash."""
    monkeypatch.setenv("TERMINAL_ENV", "local")
    # A usable start that has no .git; walk should not explode if parents blocked.
    start = tmp_path / "workspace"
    start.mkdir()
    assert _find_git_root(start) is None

    # Directly ensure blocked path never returns as git root even if present.
    assert _find_git_root(Path("/root")) is None


def test_build_context_files_prompt_tolerates_stale_root_cwd(monkeypatch, tmp_path):
    app = tmp_path / "app"
    (app / "audit").mkdir(parents=True)
    (app / "run_agent.py").write_text("#\n", encoding="utf-8")
    (app / "audit" / "note.md").write_text("hello audit\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_APP_ROOT", str(app))
    monkeypatch.setenv("TERMINAL_ENV", "local")
    # Must not raise PermissionError / crash the Desktop turn.
    prompt = build_context_files_prompt(cwd="/root", skip_soul=True)
    assert isinstance(prompt, str)


def test_session_cwd_override_root_falls_back(monkeypatch, tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    (app / "run_agent.py").write_text("#\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_APP_ROOT", str(app))
    monkeypatch.setenv("TERMINAL_ENV", "local")
    set_session_cwd("/root")
    resolved = resolve_agent_cwd()
    assert resolved == app.resolve()
    assert path_is_usable_dir(resolved)


def test_remap_covers_root_git_and_bare_root(monkeypatch, tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    (app / "run_agent.py").write_text("#\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_APP_ROOT", str(app))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()

    text = remap_stale_paths('cwd="/root" path=/root/.git docs=/root/audit/x.md')
    assert "/root/.git" not in text
    assert "/root/audit" not in text
    remapped = remap_stale_path_text("/root", app_root=str(app))
    assert remapped == str(app)


def test_migrated_session_audit_lookup_uses_app_audit(monkeypatch, tmp_path):
    app = tmp_path / "opt" / "hermes" / "app"
    audit = app / "audit"
    audit.mkdir(parents=True)
    (audit / "HERMES_TOOL_FAILURE_ROOT_CAUSE.md").write_text("root cause\n", encoding="utf-8")
    (app / "run_agent.py").write_text("#\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_APP_ROOT", str(app))
    monkeypatch.setenv("TERMINAL_ENV", "local")
    set_session_cwd("/root")
    cwd = resolve_agent_cwd()
    assert (cwd / "audit" / "HERMES_TOOL_FAILURE_ROOT_CAUSE.md").is_file()
    assert preferred_fallback_cwd() == str(app.resolve())


@pytest.mark.skipif(not Path("/opt/hermes/app").is_dir(), reason="VPS-shaped /opt/hermes only")
def test_live_opt_hermes_app_is_usable():
    assert path_is_usable_dir("/opt/hermes/app")
    assert not path_is_usable_dir("/root")
