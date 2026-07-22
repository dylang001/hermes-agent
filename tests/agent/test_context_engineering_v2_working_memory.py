"""Context Engineering V2 P2 — Working Memory store (dark / fail-open)."""

from __future__ import annotations

import json

from agent.context_engineering_v2 import (
    WorkingMemory,
    assemble_layered_messages_dark,
    estimate_working_memory_tokens,
    fold_working_memory_from_messages,
    load_working_memory,
    save_working_memory,
    trim_working_memory_to_budget,
)


class _FakeMetaDB:
    def __init__(self):
        self._store: dict[str, str] = {}

    def get_meta(self, key: str):
        return self._store.get(key)

    def set_meta(self, key: str, value: str) -> None:
        self._store[key] = value


def test_working_memory_roundtrip_json():
    wm = WorkingMemory(
        objective="Fix tax report",
        hypothesis="SAFE dumps dominate",
        decisions=["Keep compression at 0.9"],
        active_files=[{"path": "agent/foo.py", "intent": "wire WM"}],
        blockers=["Need soak"],
        branch="feature/context",
        open_questions=["Omit transcript?"],
        mutation_epoch=2,
        last_updated_api_call=12,
    )
    restored = WorkingMemory.from_dict(wm.to_dict())
    assert restored.objective == "Fix tax report"
    assert restored.mutation_epoch == 2
    assert restored.active_files[0]["path"] == "agent/foo.py"


def test_trim_drops_open_questions_before_objective():
    wm = WorkingMemory(
        objective="Keep me",
        hypothesis="h" * 4000,
        decisions=["d1", "d2", "d3", "d4"],
        open_questions=["q1", "q2", "q3"],
        active_files=[{"path": "a.py", "intent": "edit"}],
    )
    trimmed = trim_working_memory_to_budget(wm, budget_tokens=80)
    assert trimmed.objective == "Keep me"
    assert trimmed.active_files
    assert trimmed.open_questions == []
    assert estimate_working_memory_tokens(trimmed) <= 80


def test_persist_and_restore_via_session_meta():
    db = _FakeMetaDB()
    wm = WorkingMemory(objective="persist me", last_updated_api_call=3)
    assert save_working_memory("sess-1", wm, session_db=db) is True
    loaded = load_working_memory("sess-1", session_db=db)
    assert loaded is not None
    assert loaded.objective == "persist me"
    assert loaded.last_updated_api_call == 3


def test_load_missing_returns_none():
    assert load_working_memory("missing", session_db=_FakeMetaDB()) is None


def test_fold_seeds_objective_from_latest_user():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "old ask"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "Fix the tax report for July"},
    ]
    wm = fold_working_memory_from_messages(
        WorkingMemory(),
        messages,
        api_call_index=5,
    )
    assert "tax report" in wm.objective.lower()
    assert wm.last_updated_api_call == 5


def test_fold_tracks_active_files_from_mutating_tools():
    messages = [
        {"role": "user", "content": "patch the helper"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {
                        "name": "write_file",
                        "arguments": json.dumps(
                            {"path": "agent/helper.py", "content": "x"}
                        ),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "c1",
            "tool_name": "write_file",
            "content": "ok",
        },
    ]
    wm = fold_working_memory_from_messages(
        WorkingMemory(objective="patch the helper"),
        messages,
        api_call_index=2,
    )
    paths = [f.get("path") for f in wm.active_files]
    assert "agent/helper.py" in paths
    assert wm.mutation_epoch >= 1


def test_dark_assemble_returns_legacy_unchanged():
    legacy = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]
    wm = WorkingMemory(objective="hi")
    out = assemble_layered_messages_dark(legacy, working_memory=wm)
    assert out == legacy
    assert out is not legacy  # copy for safety
    assert out[0]["content"] == "sys"


def test_maybe_touch_working_memory_persists_when_enabled(tmp_path, monkeypatch):
    from agent.context_engineering_v2 import maybe_touch_working_memory

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    db = _FakeMetaDB()
    messages = [
        {"role": "user", "content": "Investigate cache stalls"},
        {"role": "assistant", "content": "looking"},
    ]
    wm = maybe_touch_working_memory(
        api_messages=messages,
        session_id="s1",
        api_call_index=1,
        session_db=db,
        config={"enabled": True, "budget_tokens": 2000},
    )
    assert wm is not None
    assert "cache" in wm.objective.lower() or "Investigate" in wm.objective
    loaded = load_working_memory("s1", session_db=db)
    assert loaded is not None


def test_maybe_touch_disabled_is_noop():
    from agent.context_engineering_v2 import maybe_touch_working_memory

    db = _FakeMetaDB()
    out = maybe_touch_working_memory(
        api_messages=[{"role": "user", "content": "x"}],
        session_id="s1",
        api_call_index=1,
        session_db=db,
        config={"enabled": False},
    )
    assert out is None
    assert db.get_meta("context_wm_v2:s1") is None
