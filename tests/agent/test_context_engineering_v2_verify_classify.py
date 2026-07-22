"""Context Engineering V2 — VERIFY classification + epoch close (lifecycle)."""

from __future__ import annotations

import json

from agent.context_engineering_v2 import (
    EvidenceClass,
    PinSet,
    classify_evidence,
    detect_verify_outcome,
    is_verify_command,
    update_pin_epoch_from_messages,
)


def _assistant_tool(tc_id: str, name: str, args: dict) -> dict:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": tc_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
        ],
    }


def _tool_result(tc_id: str, name: str, content) -> dict:
    if not isinstance(content, str):
        content = json.dumps(content)
    return {
        "role": "tool",
        "tool_call_id": tc_id,
        "tool_name": name,
        "content": content,
    }


def test_make_sure_phrase_is_not_verify():
    cmd = 'echo "make sure this works" && ls -la'
    assert not is_verify_command(cmd)
    assert classify_evidence("terminal", command=cmd) != EvidenceClass.VERIFY


def test_make_com_url_or_text_is_not_verify():
    cmd = (
        "grep -oE '.{0,80}(apollo|make.com|wordpress).{0,80}' "
        "/tmp/captions.txt | head -25"
    )
    assert not is_verify_command(cmd)
    assert classify_evidence("terminal", command=cmd) != EvidenceClass.VERIFY


def test_make_sure_in_comment_is_not_verify():
    cmd = (
        'cd ~\n'
        '# Use the tick to make sure they actually fire\n'
        'hermes cron tick 2>&1 | head -30'
    )
    assert not is_verify_command(cmd)
    assert classify_evidence("terminal", command=cmd) != EvidenceClass.VERIFY


def test_make_test_is_verify():
    assert is_verify_command("make test")
    assert classify_evidence("terminal", command="make test") == EvidenceClass.VERIFY


def test_knowledge_os_lint_registered_is_verify():
    cmd = 'python3 /opt/hermes/app/scripts/knowledge_os_lint.py "/opt/hermes/data/obsidian/Growth OS"'
    assert is_verify_command(cmd)
    assert classify_evidence("terminal", command=cmd) == EvidenceClass.VERIFY


def test_knowledge_os_lint_piped_through_head_still_verify():
    cmd = (
        'python3 /opt/hermes/app/scripts/knowledge_os_lint.py '
        '"/opt/hermes/data/obsidian/Growth OS" 2>&1 | head -200'
    )
    assert is_verify_command(cmd)
    assert classify_evidence("terminal", command=cmd) == EvidenceClass.VERIFY


def test_knowledge_os_lint_piped_through_tail_still_verify():
    cmd = (
        'python3 /opt/hermes/app/scripts/knowledge_os_lint.py '
        '"/opt/hermes/data/obsidian/Growth OS" 2>&1 | tail -60'
    )
    assert is_verify_command(cmd)
    assert classify_evidence("terminal", command=cmd) == EvidenceClass.VERIFY


def test_ruff_check_is_verify():
    assert classify_evidence("terminal", command="ruff check .") == EvidenceClass.VERIFY


def test_mypy_is_verify():
    assert classify_evidence("terminal", command="mypy src") == EvidenceClass.VERIFY


def test_npm_run_lint_is_verify():
    assert (
        classify_evidence("terminal", command="npm run lint") == EvidenceClass.VERIFY
    )


def test_npm_test_and_typecheck_and_build_are_verify():
    assert classify_evidence("terminal", command="npm test") == EvidenceClass.VERIFY
    assert (
        classify_evidence("terminal", command="npm run typecheck")
        == EvidenceClass.VERIFY
    )
    assert (
        classify_evidence("terminal", command="npm run build") == EvidenceClass.VERIFY
    )


def test_pytest_variants_are_verify():
    assert classify_evidence("terminal", command="pytest -q") == EvidenceClass.VERIFY
    assert (
        classify_evidence("terminal", command="python -m pytest tests/")
        == EvidenceClass.VERIFY
    )
    assert (
        classify_evidence("terminal", command="python3 -m pytest tests/foo.py -q")
        == EvidenceClass.VERIFY
    )


def test_arbitrary_python_script_is_not_verify():
    cmd = "python3 mutate_database.py --apply"
    assert not is_verify_command(cmd)
    assert classify_evidence("terminal", command=cmd) != EvidenceClass.VERIFY


def test_detect_verify_outcome_prefers_exit_code_over_text():
    # Text looks like failure, but exit 0 wins.
    content = json.dumps(
        {
            "output": "FAILED tests/x.py — ignore this noise",
            "exit_code": 0,
            "error": None,
        }
    )
    assert detect_verify_outcome("terminal", content) == "success"

    content_fail = json.dumps(
        {"output": "5 passed in 0.2s", "exit_code": 1, "error": None}
    )
    assert detect_verify_outcome("terminal", content_fail) == "failure"


def test_detect_verify_outcome_missing_exit_code_is_failure():
    assert (
        detect_verify_outcome("terminal", "..... 5 passed in 0.2s") == "failure"
    )


def test_verify_exit_zero_closes_epoch():
    messages = [
        {"role": "user", "content": "fix and test"},
        _assistant_tool("m1", "patch", {"path": "a.py", "diff": "+x"}),
        _tool_result("m1", "patch", "patched"),
        _assistant_tool("v1", "terminal", {"command": "ruff check ."}),
        _tool_result(
            "v1",
            "terminal",
            {"output": "All checks passed!", "exit_code": 0, "error": None},
        ),
        {"role": "assistant", "content": "green"},
    ]
    pins, events = update_pin_epoch_from_messages(
        PinSet(), messages, api_call_index=5
    )
    assert pins.open_epoch == 0
    assert pins.pins == []
    assert pins.last_close_reason == "verify_success"
    assert "verify_success" in events


def test_verify_exit_nonzero_keeps_pins():
    messages = [
        {"role": "user", "content": "fix"},
        _assistant_tool("m1", "write_file", {"path": "a.py", "content": "x"}),
        _tool_result("m1", "write_file", "ok"),
        _assistant_tool("v1", "terminal", {"command": "mypy src"}),
        _tool_result(
            "v1",
            "terminal",
            {"output": "src/a.py:1: error: x", "exit_code": 1, "error": None},
        ),
    ]
    pins, events = update_pin_epoch_from_messages(
        PinSet(), messages, api_call_index=4
    )
    assert pins.open_epoch == 1
    assert len(pins.pins) >= 2
    assert any(p.evidence_class == "verify" for p in pins.pins)
    assert "verify_failure" in events
    assert pins.last_close_reason != "verify_success"


def test_safe_success_does_not_clear_pins():
    messages = [
        {"role": "user", "content": "edit"},
        _assistant_tool("m1", "write_file", {"path": "a.py", "content": "x"}),
        _tool_result("m1", "write_file", "ok"),
        _assistant_tool("s1", "terminal", {"command": "ls -la"}),
        _tool_result(
            "s1",
            "terminal",
            {"output": "total 0", "exit_code": 0, "error": None},
        ),
    ]
    pins, events = update_pin_epoch_from_messages(
        PinSet(), messages, api_call_index=4
    )
    assert pins.open_epoch == 1
    assert any(p.tool_call_id == "m1" for p in pins.pins)
    assert "verify_success" not in events


def test_extra_registry_script_from_config(monkeypatch):
    monkeypatch.setattr(
        "agent.context_engineering_v2._load_verify_command_config",
        lambda: {
            "script_basenames": ["my_repo_check.py"],
            "extra_executables": [],
        },
    )
    cmd = "python3 tools/my_repo_check.py --strict"
    assert is_verify_command(cmd)
    assert classify_evidence("terminal", command=cmd) == EvidenceClass.VERIFY
