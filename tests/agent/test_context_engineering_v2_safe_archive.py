"""Context Engineering V2 P3 — SAFE summarise→archive (shadow only)."""

from __future__ import annotations

import json
from pathlib import Path

from agent.context_engineering_v2 import (
    EvidenceClass,
    ArchiveEntry,
    build_archive_summary,
    estimate_attended_with_real_archives,
    load_archive_index,
    maybe_run_safe_archive_shadow,
    profile_api_request_shadow,
    shadow_archive_safe_tools,
    summarise_safe_tool_result,
)


class _FakeMetaDB:
    def __init__(self):
        self._store: dict[str, str] = {}

    def get_meta(self, key: str):
        return self._store.get(key)

    def set_meta(self, key: str, value: str) -> None:
        self._store[key] = value


def test_summarise_safe_extracts_crumbs_not_raw_dump():
    dump = "total 48\n" + "\n".join(f"-rw-r--r-- 1 u g 100 Jan 1 f{i}.py" for i in range(40))
    dump += "\npackage.json\nsrc/\n"
    summary = summarise_safe_tool_result(
        tool_name="terminal",
        command="ls -la",
        content=dump,
        max_chars=300,
    )
    assert "ls -la" in summary or "terminal" in summary.lower() or "inspected" in summary.lower()
    assert "package.json" in summary or "40" in summary or "lines" in summary.lower()
    assert len(summary) < len(dump)
    assert len(summary) <= 300


def test_build_archive_summary_includes_archive_id():
    text = build_archive_summary(
        archive_id="tr_abc123",
        tool_name="read_file",
        command=None,
        content="line1\nline2\n",
        max_chars=200,
    )
    assert "tr_abc123" in text
    assert "[archived:" in text


def test_shadow_archive_persists_blob_and_index(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    db = _FakeMetaDB()
    big = "x" * 2000
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "look around"},
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
        {
            "role": "tool",
            "tool_call_id": "c1",
            "tool_name": "terminal",
            "content": big,
        },
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "continue"},
        {"role": "assistant", "content": "still going"},
    ]
    # Force recent window tiny so the SAFE dump falls outside L3.
    result = shadow_archive_safe_tools(
        messages,
        session_id="sess-a",
        api_call_index=7,
        session_db=db,
        recent_turn_budget_tokens=50,
        min_chars=100,
        hermes_home=tmp_path,
    )
    assert result["archived_new"] >= 1
    assert result["entries"]
    entry = result["entries"][0]
    assert entry.evidence_class == EvidenceClass.SAFE.value
    assert entry.tokens_raw > entry.tokens_summary
    blob = Path(entry.raw_ref)
    assert blob.is_file()
    assert blob.read_text(encoding="utf-8") == big
    index = load_archive_index("sess-a", session_db=db)
    assert any(e.archive_id == entry.archive_id for e in index)


def test_shadow_archive_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    db = _FakeMetaDB()
    messages = [
        {"role": "user", "content": "x"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c9",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps({"path": "a.py"}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "c9",
            "tool_name": "read_file",
            "content": "y" * 1500,
        },
        {"role": "assistant", "content": "done"},
        {"role": "user", "content": "next"},
    ]
    r1 = shadow_archive_safe_tools(
        messages,
        session_id="s",
        api_call_index=1,
        session_db=db,
        recent_turn_budget_tokens=20,
        min_chars=100,
        hermes_home=tmp_path,
    )
    r2 = shadow_archive_safe_tools(
        messages,
        session_id="s",
        api_call_index=2,
        session_db=db,
        recent_turn_budget_tokens=20,
        min_chars=100,
        hermes_home=tmp_path,
    )
    assert r1["archived_new"] == 1
    assert r2["archived_new"] == 0
    assert r2["archived_existing"] >= 1


def test_real_archive_attended_beats_fixed_summary_heuristic():
    """Real summaries should produce a concrete attended estimate for comparison."""
    big = "z" * 8000
    messages = [
        {"role": "system", "content": "sys" * 50},
        {"role": "user", "content": "inspect"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {
                        "name": "terminal",
                        "arguments": json.dumps({"command": "find ."}),
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "tool_name": "terminal", "content": big},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "more"},
        {"role": "assistant", "content": "y"},
    ]
    heuristic = profile_api_request_shadow(
        messages,
        tools=None,
        recent_turn_budget_tokens=80,
        working_memory_budget_tokens=0,
        safe_summary_tokens=64,
    )
    summary = build_archive_summary(
        archive_id="tr_test",
        tool_name="terminal",
        command="find .",
        content=big,
        max_chars=256,
    )
    entry = ArchiveEntry(
        archive_id="tr_test",
        kind="terminal",
        evidence_class=EvidenceClass.SAFE.value,
        created_api_call=1,
        summary=summary,
        raw_ref="",
        tokens_raw=len(big) // 4,
        tokens_summary=max(1, len(summary) // 4),
        tool_name="terminal",
        tool_call_id="c1",
        message_index=3,
    )
    real = estimate_attended_with_real_archives(
        messages,
        tools=None,
        archives_by_tool_call_id={"c1": entry},
        recent_turn_budget_tokens=80,
        working_memory_budget_tokens=0,
    )
    assert real["legacy_attended_tokens"] == heuristic["legacy_attended_tokens"]
    assert real["v2_attended_tokens_ex_wm"] < real["legacy_attended_tokens"]
    assert real["archived_safe_count"] >= 1
    # Real summary length should be used (not only the fixed 64 heuristic).
    assert real["l5_summary_tokens"] == entry.tokens_summary


def test_maybe_run_disabled_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    out = maybe_run_safe_archive_shadow(
        api_messages=[{"role": "user", "content": "hi"}],
        session_id="s",
        api_call_index=1,
        session_db=_FakeMetaDB(),
        config={"shadow_enabled": False},
    )
    assert out is None


def test_mutating_tools_are_not_archived(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    db = _FakeMetaDB()
    messages = [
        {"role": "user", "content": "edit"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "m1",
                    "type": "function",
                    "function": {
                        "name": "write_file",
                        "arguments": json.dumps({"path": "a.py", "content": "x" * 500}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "m1",
            "tool_name": "write_file",
            "content": "wrote " + ("x" * 500),
        },
        {"role": "assistant", "content": "done"},
        {"role": "user", "content": "ok"},
    ]
    result = shadow_archive_safe_tools(
        messages,
        session_id="m",
        api_call_index=1,
        session_db=db,
        recent_turn_budget_tokens=20,
        min_chars=100,
        hermes_home=tmp_path,
    )
    assert result["archived_new"] == 0
    assert load_archive_index("m", session_db=db) == []
