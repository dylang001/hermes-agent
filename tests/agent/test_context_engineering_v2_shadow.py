"""Context Engineering V2 — shadow profiler (measurement only)."""

from __future__ import annotations

import json
from pathlib import Path

from agent.context_engineering_v2 import (
    EvidenceClass,
    classify_evidence,
    profile_api_request_shadow,
    write_shadow_profile_record,
)


def test_classify_read_file_is_safe():
    assert classify_evidence("read_file") == EvidenceClass.SAFE


def test_classify_web_search_is_safe():
    assert classify_evidence("web_search") == EvidenceClass.SAFE


def test_classify_patch_is_mutating():
    assert classify_evidence("patch") == EvidenceClass.MUTATING


def test_classify_write_file_is_mutating():
    assert classify_evidence("write_file") == EvidenceClass.MUTATING


def test_classify_delegate_is_delegate():
    assert classify_evidence("delegate_task") == EvidenceClass.DELEGATE


def test_classify_terminal_ls_is_safe():
    assert classify_evidence("terminal", command="ls -la") == EvidenceClass.SAFE


def test_classify_terminal_pytest_is_verify():
    assert classify_evidence("terminal", command="pytest tests/foo.py -q") == EvidenceClass.VERIFY


def test_classify_terminal_rm_is_mutating():
    assert classify_evidence("terminal", command="rm -rf build") == EvidenceClass.MUTATING


def test_classify_terminal_git_status_is_safe():
    assert classify_evidence("terminal", command="git status") == EvidenceClass.SAFE


def test_classify_terminal_git_commit_is_mutating():
    assert (
        classify_evidence("terminal", command='git commit -m "wip"')
        == EvidenceClass.MUTATING
    )


def test_shadow_profile_estimates_safe_archive_savings():
    """Early SAFE dumps should drop out of attended_v2 while pins stay."""
    big = "x" * 8000  # ~2000 tok at chars/4
    messages = [
        {"role": "system", "content": "sys" * 100},
        {"role": "user", "content": "fix the bug"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {
                        "name": "terminal",
                        "arguments": json.dumps({"command": "ls -la"}),
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "tool_name": "terminal", "content": big},
        {"role": "assistant", "content": "looking further"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c2",
                    "type": "function",
                    "function": {
                        "name": "patch",
                        "arguments": json.dumps({"path": "a.py"}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "c2",
            "tool_name": "patch",
            "content": "diff --git a/a.py\n" + ("y" * 400),
        },
        {"role": "user", "content": "continue"},
    ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "terminal",
                "description": "run",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    rec = profile_api_request_shadow(
        messages,
        tools=tools,
        session_id="s-test",
        api_call_index=3,
        recent_turn_budget_tokens=500,  # force early SAFE out of recent window
        working_memory_budget_tokens=2000,
        safe_summary_tokens=64,
    )
    # Layering (archive SAFE outside recent) must beat legacy before WM tax.
    assert rec["v2_attended_tokens_ex_wm"] < rec["legacy_attended_tokens"]
    assert rec["estimated_savings_tokens"] > 0
    assert rec["layers"]["l1_system_tokens"] > 0
    assert rec["layers"]["l1_tools_tokens"] > 0
    assert rec["layers"]["l2_working_memory_tokens"] == 2000
    assert rec["tool_trace"]["safe_count"] >= 1
    assert rec["tool_trace"]["mutating_count"] >= 1
    assert rec["tool_trace"]["safe_chars_archived_est"] >= 8000
    # Pin (patch) stays in recent or L4 — never summarised away
    assert (
        rec["layers"]["l3_recent_tokens"] + rec["layers"]["l4_pinned_tokens"]
        >= 100
    )


def test_shadow_profile_never_archives_open_pins():
    pin_body = "FAILING TEST OUTPUT\n" + ("z" * 2000)
    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "fix"},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "t1",
                    "type": "function",
                    "function": {
                        "name": "terminal",
                        "arguments": json.dumps({"command": "pytest -q"}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "t1",
            "tool_name": "terminal",
            "content": pin_body,
        },
        # Many filler turns to push verify out of a tiny recent budget
        *[{"role": "assistant", "content": f"note {i}"} for i in range(20)],
        {"role": "user", "content": "status?"},
    ]
    rec = profile_api_request_shadow(
        messages,
        tools=[],
        session_id="s-pin",
        api_call_index=1,
        recent_turn_budget_tokens=200,
        working_memory_budget_tokens=1000,
        safe_summary_tokens=64,
    )
    assert rec["layers"]["l4_pinned_tokens"] >= len(pin_body) // 4
    assert rec["tool_trace"]["verify_count"] == 1


def test_write_shadow_record_appends_jsonl(tmp_path: Path):
    path = tmp_path / "shadow.jsonl"
    write_shadow_profile_record(path, {"session_id": "a", "v2_attended_tokens": 1})
    write_shadow_profile_record(path, {"session_id": "b", "v2_attended_tokens": 2})
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["session_id"] == "a"
    assert json.loads(lines[1])["session_id"] == "b"


def test_shadow_profiler_disabled_helper_is_noop(tmp_path: Path, monkeypatch):
    from agent.context_engineering_v2 import maybe_log_shadow_profile

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    # No config file → defaults disabled
    maybe_log_shadow_profile(
        api_messages=[{"role": "system", "content": "x"}],
        tools=[],
        session_id="s",
        api_call_index=1,
    )
    log = tmp_path / "logs" / "context_engineering_v2_shadow.jsonl"
    assert not log.exists()
