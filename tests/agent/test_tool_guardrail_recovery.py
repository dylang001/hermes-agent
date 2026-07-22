"""Recovery-oriented equivalent-probe guardrail tests."""

from __future__ import annotations

import json

from agent.tool_guardrails import (
    ToolCallGuardrailConfig,
    ToolCallGuardrailController,
    append_toolguard_guidance,
    build_failure_signature,
    classify_command_class,
    toolguard_synthetic_result,
)


def _cfg(**overrides) -> ToolCallGuardrailConfig:
    base = dict(
        hard_stop_enabled=True,
        planner_recovery_enabled=True,
        same_tool_failure_halt_after=99,
        exact_failure_block_after=99,
        equivalent_failure_warn_after=1,
        equivalent_retry_limit=2,
        strategy_pivot_limit=5,
    )
    base.update(overrides)
    return ToolCallGuardrailConfig(**base)


def _grep_fail(path: str = "/engine/cli") -> str:
    return json.dumps(
        {
            "exit_code": 1,
            "stdout": "",
            "stderr": f"grep: {path}: No matches",
        }
    )


def _missing_fail(path: str = "/root/audit") -> str:
    return json.dumps(
        {
            "exit_code": 2,
            "stdout": "",
            "stderr": f"ls: cannot access '{path}/': Permission denied",
        }
    )


def test_config_parses_recovery_knobs_without_code_changes():
    cfg = ToolCallGuardrailConfig.from_mapping(
        {
            "planner_recovery_enabled": True,
            "guardrail_local_scope": True,
            "independent_workstream_execution": True,
            "equivalent_retry_limit": 3,
            "strategy_pivot_limit": 7,
            "global_investigation_budget": 10,
            "hard_stop_after": {"equivalent_failure": 9},
        }
    )
    assert cfg.planner_recovery_enabled is True
    assert cfg.guardrail_local_scope is True
    assert cfg.independent_workstream_execution is True
    assert cfg.equivalent_retry_limit == 3
    assert cfg.equivalent_failure_halt_after == 3
    assert cfg.strategy_pivot_limit == 7
    assert cfg.global_investigation_budget == 10


def test_should_block_repeated_equivalent_grep_same_path():
    controller = ToolCallGuardrailController(_cfg())
    fail = _grep_fail("/engine/cli")
    args = {"command": "grep -R pattern /engine/cli"}

    assert classify_command_class("terminal", args) == "grep"
    sig = build_failure_signature("terminal", args, fail)
    assert sig is not None
    assert sig.failure_class == "no_matches"
    assert sig.target == "/engine/cli"

    first = controller.after_call("terminal", args, fail, failed=True)
    assert first.action == "warn"
    second = controller.after_call(
        "terminal",
        {"command": "grep -n pattern /engine/cli"},
        fail,
        failed=True,
    )
    assert second.action == "strategy_change"
    assert second.code == "strategy_change_required"
    assert second.should_halt is False

    blocked = controller.before_call("terminal", {"command": "grep foo /engine/cli"})
    assert blocked.allows_execution is False
    assert blocked.action == "strategy_change"
    payload = json.loads(toolguard_synthetic_result(blocked))
    assert payload["StrategyChangeRequired"] is True
    assert payload["planner_directive"].startswith("Current approach exhausted")


def test_should_allow_materially_different_strategies_same_path():
    controller = ToolCallGuardrailController(_cfg())
    grep_fail = _grep_fail("/engine/cli")
    controller.after_call(
        "terminal",
        {"command": "grep -R pattern /engine/cli"},
        grep_fail,
        failed=True,
    )
    controller.after_call(
        "terminal",
        {"command": "grep -n pattern /engine/cli"},
        grep_fail,
        failed=True,
    )
    assert controller.before_call(
        "terminal", {"command": "grep x /engine/cli"}
    ).allows_execution is False

    # Different command classes are independent strategies.
    for command in (
        "find /engine/cli -type f -name '*.py'",
        "git ls-files /engine/cli",
        "python -c \"import pkgutil; print(list(pkgutil.iter_modules()))\"",
    ):
        decision = controller.before_call("terminal", {"command": command})
        assert decision.allows_execution, command
        assert decision.action == "allow"


def test_should_allow_independent_smtp_workstream_after_grep_failure():
    controller = ToolCallGuardrailController(_cfg())
    fail = _grep_fail("/opt/hermes/app")
    controller.after_call(
        "terminal",
        {"command": "grep -R smtp /opt/hermes/app"},
        fail,
        failed=True,
    )
    controller.after_call(
        "terminal",
        {"command": "grep -R SMTP /opt/hermes/app"},
        fail,
        failed=True,
    )
    assert controller.halt_decision is None

    smtp = controller.before_call(
        "terminal",
        {"command": "python -c \"import smtplib; smtplib.SMTP('127.0.0.1', 25)\""},
    )
    assert smtp.allows_execution
    assert smtp.action == "allow"


def test_should_allow_database_inspection_after_grep_failure():
    controller = ToolCallGuardrailController(_cfg())
    fail = _grep_fail("/opt/hermes/app")
    controller.after_call(
        "terminal",
        {"command": "grep -R schema /opt/hermes/app"},
        fail,
        failed=True,
    )
    controller.after_call(
        "terminal",
        {"command": "grep -R tables /opt/hermes/app"},
        fail,
        failed=True,
    )

    db = controller.before_call(
        "terminal",
        {"command": "sqlite3 /var/lib/app/state.db '.tables'"},
    )
    assert db.allows_execution


def test_should_allow_delegate_task_after_grep_failure():
    controller = ToolCallGuardrailController(_cfg())
    fail = _grep_fail("/opt/hermes/app")
    controller.after_call(
        "terminal",
        {"command": "grep -R engine /opt/hermes/app"},
        fail,
        failed=True,
    )
    controller.after_call(
        "terminal",
        {"command": "grep -R Engine /opt/hermes/app"},
        fail,
        failed=True,
    )

    delegate = controller.before_call(
        "delegate_task",
        {"goal": "Locate the CLI entrypoint", "role": "leaf"},
    )
    assert delegate.allows_execution
    assert controller.halt_decision is None


def test_successful_pivot_resets_equivalent_retry_counter():
    controller = ToolCallGuardrailController(_cfg())
    fail = _missing_fail("/root/audit")
    controller.after_call(
        "terminal",
        {"command": "ls /root/audit"},
        fail,
        failed=True,
    )
    pivot = controller.after_call(
        "terminal",
        {"command": "ls -la /root/audit"},
        fail,
        failed=True,
    )
    assert pivot.action == "strategy_change"

    # Different strategy succeeds under the same workstream (/root/audit).
    ok = controller.after_call(
        "terminal",
        {"command": "find /root/audit -maxdepth 2 -type d 2>/dev/null || true"},
        json.dumps({"exit_code": 0, "stdout": "/root/audit\n", "stderr": ""}),
        failed=False,
    )
    assert ok.action == "allow"

    # Equivalent retry budget is fresh; first ls failure warns again, does not block.
    again = controller.after_call(
        "terminal",
        {"command": "ls /root/audit"},
        fail,
        failed=True,
    )
    assert again.action == "warn"
    assert controller.before_call(
        "terminal", {"command": "ls /root/audit"}
    ).allows_execution


def test_strategy_pivots_exhausted_halts_only_after_budget():
    controller = ToolCallGuardrailController(_cfg(strategy_pivot_limit=2))
    path = "/engine/cli"
    fail = _grep_fail(path)

    strategies = [
        ("grep -R a /engine/cli", "grep -R b /engine/cli"),
        ("ls /engine/cli", "ls -la /engine/cli"),
        ("find /engine/cli -type f", "find /engine/cli -name '*'"),
    ]
    decisions = []
    for first_cmd, second_cmd in strategies:
        decisions.append(
            controller.after_call("terminal", {"command": first_cmd}, fail, failed=True)
        )
        decisions.append(
            controller.after_call("terminal", {"command": second_cmd}, fail, failed=True)
        )

    # Two pivots recorded (grep, ls); third strategy exhaustion escalates.
    assert decisions[1].action == "strategy_change"
    assert decisions[3].action == "strategy_change"
    assert decisions[5].action == "halt"
    assert decisions[5].code == "strategy_pivots_exhausted"
    assert decisions[5].should_halt is True


def test_different_failure_signatures_do_not_share_retry_counter():
    controller = ToolCallGuardrailController(_cfg())
    no_match = _grep_fail("/opt/hermes/app")
    missing = json.dumps(
        {
            "exit_code": 2,
            "stdout": "",
            "stderr": "grep: /opt/hermes/app: No such file or directory",
        }
    )
    controller.after_call(
        "terminal",
        {"command": "grep -R a /opt/hermes/app"},
        no_match,
        failed=True,
    )
    # Different failure_class → independent counter; still just a warning.
    second = controller.after_call(
        "terminal",
        {"command": "grep -R a /opt/hermes/missing"},
        missing,
        failed=True,
    )
    assert second.action == "warn"
    assert second.code == "equivalent_path_failure_warning"


def test_append_guidance_includes_strategy_change_payload():
    controller = ToolCallGuardrailController(_cfg())
    fail = _grep_fail("/engine/cli")
    controller.after_call(
        "terminal",
        {"command": "grep a /engine/cli"},
        fail,
        failed=True,
    )
    decision = controller.after_call(
        "terminal",
        {"command": "grep b /engine/cli"},
        fail,
        failed=True,
    )
    guided = append_toolguard_guidance(fail, decision)
    assert "StrategyChangeRequired" in guided
    assert "suggested_alternative_strategies" in guided


def test_telemetry_events_queued_for_runtime():
    controller = ToolCallGuardrailController(_cfg())
    fail = _grep_fail("/engine/cli")
    controller.after_call(
        "terminal",
        {"command": "grep a /engine/cli"},
        fail,
        failed=True,
    )
    controller.after_call(
        "terminal",
        {"command": "grep b /engine/cli"},
        fail,
        failed=True,
    )
    events = controller.drain_telemetry()
    assert any(e["event"] == "guardrail_strategy_change" for e in events)
    assert any(e.get("failure_signature") for e in events)
