"""Context Engineering V2 P6 — archive retrieve + soak logging."""

from __future__ import annotations

from pathlib import Path

from agent.context_engineering_v2 import (
    ArchiveEntry,
    EvidenceClass,
    append_retrieved_to_messages,
    budget_raw_segment,
    clear_pending_retrieves,
    enqueue_pending_retrieve,
    get_archive_raw,
    list_archive_summaries,
    load_pending_retrieves,
    log_soak_record,
    maybe_auto_enqueue_verify_failure_retrieves,
    resolve_archive_entry,
    save_archive_index,
)


class _FakeMetaDB:
    def __init__(self):
        self._store: dict[str, str] = {}

    def get_meta(self, key: str):
        return self._store.get(key)

    def set_meta(self, key: str, value: str) -> None:
        self._store[key] = value


def _seed_archive(tmp_path: Path, db: _FakeMetaDB, session_id: str = "s1") -> ArchiveEntry:
    raw = "LINE\n" * 2000  # bulky
    blob_dir = tmp_path / "context_archive" / session_id
    blob_dir.mkdir(parents=True)
    archive_id = "tr_abc12345"
    blob = blob_dir / f"{archive_id}.txt"
    blob.write_text(raw, encoding="utf-8")
    entry = ArchiveEntry(
        archive_id=archive_id,
        kind="terminal",
        evidence_class=EvidenceClass.SAFE.value,
        created_api_call=3,
        summary="[archived:tr_abc12345] ls inspected.",
        raw_ref=str(blob),
        tokens_raw=len(raw) // 4,
        tokens_summary=10,
        tool_name="terminal",
        tool_call_id="c1",
        command="ls -la",
        message_index=4,
    )
    save_archive_index(session_id, [entry], session_db=db)
    return entry


def test_list_and_resolve_archive(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    db = _FakeMetaDB()
    entry = _seed_archive(tmp_path, db)
    listed = list_archive_summaries("s1", session_db=db)
    assert len(listed) == 1
    assert listed[0]["archive_id"] == entry.archive_id
    resolved = resolve_archive_entry("s1", entry.archive_id, session_db=db)
    assert resolved is not None
    assert resolved.archive_id == entry.archive_id


def test_get_archive_raw_is_budgeted(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    db = _FakeMetaDB()
    entry = _seed_archive(tmp_path, db)
    payload = get_archive_raw(
        "s1",
        entry.archive_id,
        session_db=db,
        max_tokens=50,
        offset_chars=0,
    )
    assert payload["ok"] is True
    assert payload["archive_id"] == entry.archive_id
    assert payload["truncated"] is True
    assert payload["tokens_est"] <= 50
    assert len(payload["content"]) < 2000 * 5


def test_budget_raw_segment_offset():
    text = "abcdefghijklmnopqrstuvwxyz" * 100
    a = budget_raw_segment(text, max_tokens=10, offset_chars=0)
    b = budget_raw_segment(text, max_tokens=10, offset_chars=a["next_offset"])
    assert a["content"] != b["content"]
    assert a["truncated"] is True


def test_pending_retrieve_queue_and_append(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    db = _FakeMetaDB()
    entry = _seed_archive(tmp_path, db)
    assert enqueue_pending_retrieve(
        "s1",
        entry.archive_id,
        session_db=db,
        reason="tool_get",
    )
    pending = load_pending_retrieves("s1", session_db=db)
    assert len(pending) == 1
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]
    out, injected = append_retrieved_to_messages(
        msgs,
        session_id="s1",
        session_db=db,
        max_tokens_per=80,
    )
    assert injected >= 1
    assert out[-1]["role"] == "user"
    assert "tr_abc12345" in out[-1]["content"]
    assert "hermes_context_archive" in out[-1]["content"]
    # Queue cleared after inject
    assert load_pending_retrieves("s1", session_db=db) == []


def test_clear_pending():
    db = _FakeMetaDB()
    enqueue_pending_retrieve("s", "tr_x", session_db=db)
    clear_pending_retrieves("s", session_db=db)
    assert load_pending_retrieves("s", session_db=db) == []


def test_auto_enqueue_on_verify_failure(tmp_path, monkeypatch):
    from agent.context_engineering_v2 import PinSet, PinnedEvidence

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    db = _FakeMetaDB()
    entry = _seed_archive(tmp_path, db)
    pins = PinSet(
        open_epoch=1,
        pins=[
            PinnedEvidence(
                tool_call_id="m1",
                tool_name="write_file",
                evidence_class="mutating",
                mutation_epoch=1,
                message_index=1,
                chars=10,
                tokens_est=3,
                path="src/a.py",
            ),
            PinnedEvidence(
                tool_call_id="v1",
                tool_name="terminal",
                evidence_class="verify",
                mutation_epoch=1,
                message_index=2,
                chars=20,
                tokens_est=5,
                command="pytest",
                verify_outcome="failure",
            ),
        ],
    )
    # Seed a second archive whose summary/command mentions src
    entry2 = ArchiveEntry(
        archive_id="tr_pathsafe1",
        kind="read_file",
        evidence_class="safe",
        created_api_call=1,
        summary="read src/a.py",
        raw_ref=str(tmp_path / "context_archive" / "s1" / "tr_abc12345.txt"),
        tokens_raw=100,
        tokens_summary=5,
        tool_name="read_file",
        tool_call_id="c9",
        command="src/a.py",
    )
    save_archive_index("s1", [entry, entry2], session_db=db)
    n = maybe_auto_enqueue_verify_failure_retrieves(
        "s1",
        pin_set=pins,
        session_db=db,
    )
    assert n >= 1
    pending = load_pending_retrieves("s1", session_db=db)
    assert any(p.get("archive_id") == "tr_pathsafe1" for p in pending)


def test_soak_log_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    path = log_soak_record(
        {
            "session_id": "s",
            "arm": "layered",
            "step": "inspect",
            "legacy_tokens_est": 1000,
            "layered_tokens_est": 400,
            "retrieve_count": 1,
        },
        log_filename="soak_test.jsonl",
    )
    assert path.is_file()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert "layered" in lines[0]
