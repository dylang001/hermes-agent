"""Context Engineering V2 P4 — MUTATING pin/unpin epoch (dark)."""

from __future__ import annotations

import json

from agent.context_engineering_v2 import (
    PinSet,
    WorkingMemory,
    detect_verify_outcome,
    load_pin_set,
    maybe_run_pin_epoch_shadow,
    save_pin_set,
    update_pin_epoch_from_messages,
)


class _FakeMetaDB:
    def __init__(self):
        self._store: dict[str, str] = {}

    def get_meta(self, key: str):
        return self._store.get(key)

    def set_meta(self, key: str, value: str) -> None:
        self._store[key] = value


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


def _tool_result(tc_id: str, name: str, content: str) -> dict:
    return {
        "role": "tool",
        "tool_call_id": tc_id,
        "tool_name": name,
        "content": content,
    }


def test_mutating_opens_epoch_and_pins():
    messages = [
        {"role": "user", "content": "fix helper"},
        _assistant_tool("m1", "write_file", {"path": "a.py", "content": "x"}),
        _tool_result("m1", "write_file", "wrote a.py"),
        {"role": "assistant", "content": "patched"},
    ]
    pins, events = update_pin_epoch_from_messages(
        PinSet(),
        messages,
        api_call_index=3,
        working_memory=WorkingMemory(objective="fix helper"),
    )
    assert pins.open_epoch == 1
    assert any(p.tool_call_id == "m1" for p in pins.pins)
    assert "epoch_opened" in events or "pinned" in events


def test_verify_success_unpins_epoch():
    messages = [
        {"role": "user", "content": "fix and test"},
        _assistant_tool("m1", "patch", {"path": "a.py", "diff": "+x"}),
        _tool_result("m1", "patch", "patched"),
        _assistant_tool("v1", "terminal", {"command": "pytest tests/test_a.py -q"}),
        _tool_result(
            "v1",
            "terminal",
            json.dumps(
                {"output": "..... 5 passed in 0.2s", "exit_code": 0, "error": None}
            ),
        ),
        {"role": "assistant", "content": "green"},
    ]
    pins, _ = update_pin_epoch_from_messages(
        PinSet(),
        messages,
        api_call_index=5,
    )
    assert pins.open_epoch == 0
    assert pins.pins == []
    assert pins.last_closed_epoch == 1
    assert pins.last_close_reason == "verify_success"


def test_verify_failure_keeps_pins():
    messages = [
        {"role": "user", "content": "fix"},
        _assistant_tool("m1", "write_file", {"path": "a.py", "content": "x"}),
        _tool_result("m1", "write_file", "ok"),
        _assistant_tool("v1", "terminal", {"command": "pytest -q"}),
        _tool_result(
            "v1",
            "terminal",
            json.dumps(
                {
                    "output": "FAILED tests/test_a.py::test_x - assert 1 == 2\n1 failed",
                    "exit_code": 1,
                    "error": None,
                }
            ),
        ),
    ]
    pins, _ = update_pin_epoch_from_messages(PinSet(), messages, api_call_index=4)
    assert pins.open_epoch == 1
    assert len(pins.pins) >= 2  # mutate + verify
    assert any(p.evidence_class == "verify" for p in pins.pins)


def test_user_abandon_clears_pins():
    base = PinSet(open_epoch=2, pins=[])
    # seed via mutate then abandon
    messages = [
        {"role": "user", "content": "edit file"},
        _assistant_tool("m1", "write_file", {"path": "b.py", "content": "y"}),
        _tool_result("m1", "write_file", "ok"),
        {"role": "user", "content": "cancel that, nevermind"},
    ]
    pins, events = update_pin_epoch_from_messages(PinSet(), messages, api_call_index=4)
    assert pins.open_epoch == 0
    assert pins.pins == []
    assert "abandoned" in events or pins.last_close_reason == "user_abandon"


def test_pin_set_persist_roundtrip():
    db = _FakeMetaDB()
    pins = update_pin_epoch_from_messages(
        PinSet(),
        [
            {"role": "user", "content": "x"},
            _assistant_tool("m1", "write_file", {"path": "c.py", "content": "z"}),
            _tool_result("m1", "write_file", "ok"),
        ],
        api_call_index=1,
    )[0]
    assert pins.open_epoch == 1
    assert save_pin_set("s1", pins, session_db=db)
    loaded = load_pin_set("s1", session_db=db)
    assert loaded is not None
    assert loaded.open_epoch == 1
    assert loaded.pins[0].tool_call_id == "m1"


def test_detect_verify_outcome_helpers():
    # exit_code is authoritative for terminal; bare prose without exit_code → failure
    assert detect_verify_outcome("terminal", '{"exit_code": 0, "output": "ok"}') == "success"
    assert detect_verify_outcome("terminal", '{"exit_code": 1, "output": "boom"}') == "failure"
    assert detect_verify_outcome("terminal", "exit code 1\nError: boom") == "failure"
    assert detect_verify_outcome("pytest", '{"exit_code": 0, "output": "5 passed"}') == "success"
    assert detect_verify_outcome("pytest", "5 passed in 0.1s") == "failure"
    assert detect_verify_outcome("read_file", "hello") is None


def test_safe_archive_must_not_unpin_or_clear_mutate_pins():
    """SAFE inspect after mutate must leave the epoch open."""
    messages = [
        {"role": "user", "content": "edit"},
        _assistant_tool("m1", "write_file", {"path": "d.py", "content": "q"}),
        _tool_result("m1", "write_file", "ok"),
        _assistant_tool("s1", "terminal", {"command": "ls -la"}),
        _tool_result("s1", "terminal", "total 1\nfile"),
        {"role": "assistant", "content": "still working"},
    ]
    pins, _ = update_pin_epoch_from_messages(PinSet(), messages, api_call_index=3)
    assert pins.open_epoch == 1
    assert any(p.tool_call_id == "m1" for p in pins.pins)


def test_maybe_run_disabled_noop():
    out = maybe_run_pin_epoch_shadow(
        api_messages=[{"role": "user", "content": "hi"}],
        session_id="s",
        api_call_index=1,
        session_db=_FakeMetaDB(),
        config={"enabled": False},
    )
    assert out is None


def test_maybe_run_enabled_persists_and_syncs_wm(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    db = _FakeMetaDB()
    wm = WorkingMemory(objective="fix it")
    messages = [
        {"role": "user", "content": "fix it"},
        _assistant_tool("m1", "write_file", {"path": "e.py", "content": "1"}),
        _tool_result("m1", "write_file", "ok"),
    ]
    out = maybe_run_pin_epoch_shadow(
        api_messages=messages,
        session_id="sess",
        api_call_index=2,
        session_db=db,
        working_memory=wm,
        config={"enabled": True, "persist": True},
    )
    assert out is not None
    assert out["open_epoch"] == 1
    assert out["pin_count"] >= 1
    assert out["mutates_prompt"] is False
    loaded = load_pin_set("sess", session_db=db)
    assert loaded and loaded.open_epoch == 1
    wm2 = out.get("_working_memory")
    assert wm2 is not None
    assert wm2.mutation_epoch == 1
