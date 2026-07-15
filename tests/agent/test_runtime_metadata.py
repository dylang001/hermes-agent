"""Runtime metadata + stale-path remapping for post-migration deployments."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent.memory_manager import build_memory_context_block, sanitize_context
from agent.runtime_metadata import (
    RuntimeMetadata,
    collect_runtime_metadata,
    discover_under_roots,
    remap_stale_paths,
    resolve_app_root,
)
from agent.tool_guardrails import (
    ToolCallGuardrailConfig,
    ToolCallGuardrailController,
    equivalent_failure_key,
    extract_absolute_path_targets,
    looks_like_missing_path_failure,
)


def test_resolve_app_root_points_at_checkout_with_run_agent():
    root = resolve_app_root()
    assert (root / "run_agent.py").exists() or (root / "pyproject.toml").exists()


def test_collect_runtime_metadata_includes_authoritative_fields(monkeypatch, tmp_path):
    hermes_home = tmp_path / "home"
    hermes_home.mkdir()
    app = tmp_path / "app"
    app.mkdir()
    (app / "run_agent.py").write_text("# stub\n", encoding="utf-8")
    cwd = tmp_path / "cwd"
    cwd.mkdir()

    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("HERMES_APP_ROOT", str(app))
    monkeypatch.setenv("TERMINAL_ENV", "local")
    monkeypatch.chdir(cwd)

    meta = collect_runtime_metadata()
    assert meta.app_root == str(app.resolve())
    assert meta.hermes_home == str(hermes_home.resolve())
    assert meta.cwd == str(cwd.resolve())
    assert meta.user
    assert "Authoritative runtime" in meta.as_prompt_block()
    assert str(app.resolve()) in meta.writable_roots or str(hermes_home.resolve()) in meta.writable_roots


def test_remap_stale_root_paths_on_opt_hermes_deployment(monkeypatch, tmp_path):
    hermes_home = tmp_path / "opt-hermes-home"
    hermes_home.mkdir()
    app = tmp_path / "opt-hermes-app"
    (app / "audit").mkdir(parents=True)
    (app / "run_agent.py").write_text("# stub\n", encoding="utf-8")

    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("HERMES_APP_ROOT", str(app))

    remapped = remap_stale_paths(
        "See /root/audit/MASTER.md and /root/.hermes/config.yaml under /usr/local/lib/hermes-agent"
    )
    assert "/root/audit" not in remapped
    assert "/root/.hermes" not in remapped
    assert "/usr/local/lib/hermes-agent" not in remapped
    assert str(app / "audit") in remapped
    assert str(hermes_home) in remapped
    assert str(app) in remapped


def test_sanitize_context_rewrites_stale_mem0_paths(monkeypatch, tmp_path):
    hermes_home = tmp_path / "home"
    hermes_home.mkdir()
    app = tmp_path / "app"
    (app / "audit").mkdir(parents=True)
    (app / "run_agent.py").write_text("# stub\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("HERMES_APP_ROOT", str(app))

    clean = sanitize_context("- docs live at /root/audit/report.md")
    assert "/root/audit" not in clean
    assert "report.md" in clean

    block = build_memory_context_block("- docs live at /root/audit/report.md")
    assert "system prompt wins" in block.lower()
    assert "/root/audit" not in block


def test_discover_missing_directory_under_writable_roots(tmp_path):
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    target = root_b / "audit" / "notes"
    target.mkdir(parents=True)

    found = discover_under_roots("audit/notes", roots=(str(root_a), str(root_b)))
    assert found == [str(target.resolve())]


def test_equivalent_terminal_path_failures_halt_after_two():
    controller = ToolCallGuardrailController(
        ToolCallGuardrailConfig(
            hard_stop_enabled=True,
            same_tool_failure_halt_after=99,
            exact_failure_block_after=99,
            equivalent_failure_warn_after=1,
            equivalent_failure_halt_after=2,
        )
    )
    fail = '{"exit_code":2,"stdout":"","stderr":"ls: cannot access \'/root/audit/\': Permission denied"}'
    assert looks_like_missing_path_failure(fail)

    first = controller.after_call(
        "terminal",
        {"command": "ls -la /root/audit/ 2>/dev/null"},
        fail,
        failed=True,
    )
    assert first.action == "warn"
    assert first.code == "equivalent_path_failure_warning"

    second = controller.after_call(
        "terminal",
        {"command": 'echo "ok"; ls /root/audit/'},
        fail,
        failed=True,
    )
    assert second.action == "halt"
    assert second.code == "equivalent_path_failure_halt"
    assert second.count == 2

    blocked = controller.before_call(
        "terminal",
        {"command": "pwd; ls -la /root/audit"},
    )
    assert blocked.action == "block"
    assert blocked.code == "equivalent_path_failure_block"


def test_extract_absolute_path_targets_from_terminal_command():
    targets = extract_absolute_path_targets(
        "terminal",
        {"command": 'echo test; ls /root/audit/ && cat /opt/hermes/app/audit/x.md'},
    )
    assert "/root/audit" in targets or "/root/audit/" in {t.rstrip("/") for t in targets}
    assert any(t.startswith("/opt/hermes/app/audit") for t in targets)
    key = equivalent_failure_key("terminal", {"command": "ls /root/audit/"})
    assert key == "terminal:/root/audit"


def test_session_resume_remembers_opt_hermes_not_root(monkeypatch, tmp_path):
    """Old-session text mentioning /root must not beat live /opt/hermes facts."""
    hermes_home = Path("/opt/hermes/home")
    app = Path("/opt/hermes/app")
    if not app.is_dir() or not hermes_home.is_dir():
        # Local macOS checkout: simulate with env overrides.
        hermes_home = tmp_path / "opt" / "hermes" / "home"
        app = tmp_path / "opt" / "hermes" / "app"
        (app / "audit").mkdir(parents=True)
        hermes_home.mkdir(parents=True)
        (app / "run_agent.py").write_text("# stub\n", encoding="utf-8")
        monkeypatch.setenv("HERMES_HOME", str(hermes_home))
        monkeypatch.setenv("HERMES_APP_ROOT", str(app))

    recalled = (
        "Previous VPS used HERMES_HOME=/root/.hermes and audit at /root/audit/. "
        "Also checkout /usr/local/lib/hermes-agent."
    )
    remapped = remap_stale_paths(recalled)
    meta = collect_runtime_metadata()
    assert "/root/audit" not in remapped
    assert "/root/.hermes" not in remapped
    assert meta.hermes_home.endswith("hermes/home") or "hermes" in meta.hermes_home
    assert "Authoritative runtime" in meta.as_prompt_block()
    assert meta.app_root
