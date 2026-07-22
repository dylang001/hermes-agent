"""Context Engineering V2 P5 — layered assemble for inspect steps."""

from __future__ import annotations

import json

from agent.context_engineering_v2 import (
    ArchiveEntry,
    EvidenceClass,
    PinSet,
    PinnedEvidence,
    WorkingMemory,
    assemble_layered_api_messages,
    classify_assemble_step,
    maybe_assemble_layered_api_messages,
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


def _tool(tc_id: str, name: str, content: str) -> dict:
    return {
        "role": "tool",
        "tool_call_id": tc_id,
        "tool_name": name,
        "content": content,
    }


def _legacy_messages() -> list:
    big = "DUMP:" + ("x" * 4000)
    return [
        {"role": "system", "content": "You are Hermes."},
        {"role": "user", "content": "explore the repo"},
        _assistant_tool("c1", "terminal", {"command": "ls -la"}),
        _tool("c1", "terminal", big),
        {"role": "assistant", "content": "saw files"},
        {"role": "user", "content": "what is in src?"},
        _assistant_tool("c2", "read_file", {"path": "src/a.py"}),
        _tool("c2", "read_file", "print('hi')\n" * 20),
        {"role": "assistant", "content": "looking"},
        {"role": "user", "content": "continue inspecting"},
    ]


def test_classify_inspect_when_no_open_epoch():
    msgs = _legacy_messages()
    assert classify_assemble_step(msgs, PinSet()) == "inspect"


def test_classify_mutate_when_epoch_open():
    pins = PinSet(open_epoch=1, pins=[
        PinnedEvidence(
            tool_call_id="m1",
            tool_name="write_file",
            evidence_class="mutating",
            mutation_epoch=1,
            message_index=2,
            chars=10,
            tokens_est=3,
        )
    ])
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "edit"},
        _assistant_tool("m1", "write_file", {"path": "a.py", "content": "x"}),
        _tool("m1", "write_file", "ok"),
    ]
    assert classify_assemble_step(msgs, pins) == "mutate"


def test_inspect_assemble_omits_old_safe_dump_uses_summary():
    legacy = _legacy_messages()
    big = legacy[3]["content"]
    arch = ArchiveEntry(
        archive_id="tr_test1",
        kind="terminal",
        evidence_class=EvidenceClass.SAFE.value,
        created_api_call=1,
        summary="[archived:tr_test1] ls inspected.\nKey findings:\n- 1 lines",
        raw_ref="",
        tokens_raw=len(big) // 4,
        tokens_summary=20,
        tool_name="terminal",
        tool_call_id="c1",
        message_index=3,
    )
    wm = WorkingMemory(objective="explore the repo")
    out = assemble_layered_api_messages(
        legacy,
        working_memory=wm,
        pin_set=PinSet(),
        archives_by_tool_call_id={"c1": arch},
        step="inspect",
        recent_turn_budget_tokens=500,  # keep only the tail
    )
    assert out[0]["role"] == "system"
    assert out[0]["content"] == "You are Hermes."
    # Old SAFE dump body must not appear verbatim.
    joined = json.dumps(out)
    assert big not in joined
    assert "tr_test1" in joined or "archived:" in joined
    # WM injected somewhere after system.
    assert "explore the repo" in joined
    # Must be smaller than legacy attended content.
    assert len(joined) < len(json.dumps(legacy))


def test_inspect_assemble_keeps_open_pins_verbatim():
    pin_body = "DIFF:" + ("y" * 2000)
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "fix"},
        _assistant_tool("m1", "write_file", {"path": "a.py", "content": "z"}),
        _tool("m1", "write_file", pin_body),
        {"role": "user", "content": "now just ls please"},
    ]
    pins = PinSet(
        open_epoch=1,
        mutation_epoch_counter=1,
        pins=[
            PinnedEvidence(
                tool_call_id="m1",
                tool_name="write_file",
                evidence_class="mutating",
                mutation_epoch=1,
                message_index=3,
                chars=len(pin_body),
                tokens_est=len(pin_body) // 4,
                path="a.py",
            )
        ],
    )
    # Even if step were inspect, pins must survive — but classify would be mutate.
    # Force inspect assemble with pins present to verify pin retention invariant.
    out = assemble_layered_api_messages(
        msgs,
        working_memory=WorkingMemory(objective="fix"),
        pin_set=pins,
        archives_by_tool_call_id={},
        step="inspect",
        recent_turn_budget_tokens=80,
    )
    joined = json.dumps(out)
    assert pin_body in joined


def test_mutate_step_returns_legacy_unchanged():
    legacy = _legacy_messages()
    out = assemble_layered_api_messages(
        legacy,
        working_memory=WorkingMemory(objective="x"),
        pin_set=PinSet(open_epoch=1),
        archives_by_tool_call_id={},
        step="mutate",
        recent_turn_budget_tokens=200,
    )
    assert out == [dict(m) for m in legacy]


def test_tool_pairs_not_orphaned():
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u1"},
        _assistant_tool("t1", "read_file", {"path": "a.py"}),
        _tool("t1", "read_file", "content-a"),
        {"role": "assistant", "content": "mid"},
        {"role": "user", "content": "u2 recent"},
    ]
    out = assemble_layered_api_messages(
        msgs,
        working_memory=WorkingMemory(objective="u2"),
        pin_set=PinSet(),
        archives_by_tool_call_id={},
        step="inspect",
        recent_turn_budget_tokens=200,
    )
    # Every tool result must have a preceding assistant with matching tool_call id
    # in the assembled list (not necessarily immediately, but present).
    tc_ids_from_assistant = set()
    for m in out:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                if isinstance(tc, dict) and tc.get("id"):
                    tc_ids_from_assistant.add(tc["id"])
    for m in out:
        if m.get("role") == "tool":
            assert m.get("tool_call_id") in tc_ids_from_assistant


def test_maybe_assemble_disabled_returns_none():
    assert (
        maybe_assemble_layered_api_messages(
            api_messages=_legacy_messages(),
            working_memory=WorkingMemory(objective="x"),
            pin_set=PinSet(),
            archives_by_tool_call_id={},
            config={"enabled": False},
        )
        is None
    )


def test_maybe_assemble_inspect_rewrites_when_enabled():
    legacy = _legacy_messages()
    arch = ArchiveEntry(
        archive_id="tr_x",
        kind="terminal",
        evidence_class="safe",
        created_api_call=1,
        summary="[archived:tr_x] summary",
        raw_ref="",
        tokens_raw=1000,
        tokens_summary=10,
        tool_name="terminal",
        tool_call_id="c1",
    )
    out = maybe_assemble_layered_api_messages(
        api_messages=legacy,
        working_memory=WorkingMemory(objective="explore the repo"),
        pin_set=PinSet(),
        archives_by_tool_call_id={"c1": arch},
        config={
            "enabled": True,
            "inspect_steps": True,
            "recent_turn_budget_tokens": 400,
            "fail_open": True,
        },
    )
    assert out is not None
    assert out["step"] == "inspect"
    assert out["mutates_prompt"] is True
    assert out["messages"][0]["role"] == "system"
    assert legacy[3]["content"] not in json.dumps(out["messages"])


def test_fail_open_on_bad_wm_still_returns_legacy_path():
    """Assembler must not raise; caller uses legacy when result is None/error."""
    # Empty messages with enabled flag — should fail open to None or legacy marker
    out = maybe_assemble_layered_api_messages(
        api_messages=[],
        working_memory=None,
        pin_set=None,
        archives_by_tool_call_id={},
        config={"enabled": True, "inspect_steps": True, "fail_open": True},
    )
    # No useful layering possible — fail open (None means keep legacy).
    assert out is None or out.get("messages") == []
