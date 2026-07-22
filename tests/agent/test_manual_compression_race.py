"""Race / attach-to-winner coverage for manual /compress."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agent.manual_compression_feedback import summarize_manual_compression
from agent.manual_compression_wait import (
    find_compression_child_session_id,
    wait_for_peer_compression,
)
from hermes_state import SessionDB


def _seed_parent(db: SessionDB, sid: str, n_messages: int = 8) -> None:
    db.create_session(session_id=sid, source="test")
    for i in range(n_messages):
        role = "user" if i % 2 == 0 else "assistant"
        db.append_message(sid, role, f"msg-{i}")


def test_force_true_still_serializes_on_compression_lock(tmp_path: Path) -> None:
    """force=True bypasses cooldown only — two compressors must not both rotate."""
    import os
    from unittest.mock import patch

    db_path = tmp_path / "state.db"
    db = SessionDB(db_path=db_path)
    parent = "parent_force_lock"
    _seed_parent(db, parent, 10)

    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
        from run_agent import AIAgent

        agents = []
        for _ in range(2):
            agent = AIAgent(
                api_key="test-key",
                base_url="https://openrouter.ai/api/v1",
                model="test/model",
                quiet_mode=True,
                session_db=db,
                session_id=parent,
                skip_context_files=True,
                skip_memory=True,
            )
            compressor = MagicMock()
            compressor.compress.side_effect = lambda *a, **k: (
                time.sleep(0.3),
                [
                    {"role": "user", "content": "[CONTEXT COMPACTION] summary"},
                    {"role": "user", "content": "tail"},
                ],
            )[1]
            compressor.compression_count = 1
            compressor.last_prompt_tokens = 0
            compressor.last_completion_tokens = 0
            compressor._last_summary_error = None
            compressor._last_compress_aborted = False
            agent.context_compressor = compressor
            agent.compression_in_place = False
            agents.append(agent)

    history = db.get_messages_as_conversation(parent)
    results: list = [None, None]
    errors: list = []

    def _run(idx: int) -> None:
        try:
            results[idx] = agents[idx]._compress_context(
                history, None, approx_tokens=12_000, force=True
            )
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    t0 = threading.Thread(target=_run, args=(0,))
    t1 = threading.Thread(target=_run, args=(1,))
    t0.start()
    t1.start()
    t0.join(timeout=10)
    t1.join(timeout=10)
    assert not errors

    children = db._conn.execute(
        "SELECT id FROM sessions WHERE parent_session_id = ?", (parent,)
    ).fetchall()
    assert len(children) == 1, f"expected exactly one child, got {children}"

    skip_flags = [
        getattr(a, "_last_compress_skip_reason", None) for a in agents
    ]
    assert "concurrent_lock" in skip_flags or "already_rotated" in skip_flags


def test_wait_attaches_to_winner_child_tip(tmp_path: Path) -> None:
    db = SessionDB(db_path=tmp_path / "state.db")
    parent = "parent_wait"
    child = "child_wait"
    _seed_parent(db, parent, 6)
    db.end_session(parent, end_reason="compression")
    db.create_session(session_id=child, source="test", parent_session_id=parent)
    for i, content in enumerate(
        ["[CONTEXT COMPACTION] summary", "kept-tail-1", "kept-tail-2"]
    ):
        db.append_message(child, "user" if i == 0 else "assistant", content)

    assert find_compression_child_session_id(db, parent) == child

    agent = SimpleNamespace(session_id=parent)
    result = wait_for_peer_compression(
        session_db=db,
        parent_session_id=parent,
        agent=agent,
        timeout_seconds=2.0,
        poll_seconds=0.05,
        before_message_count=6,
    )
    assert result.status == "completed"
    assert result.session_id == child
    assert len(result.messages) == 3
    assert "COMPACTION" in (result.messages[0].get("content") or "")


def test_wait_timeout_when_peer_never_finishes(tmp_path: Path) -> None:
    db = SessionDB(db_path=tmp_path / "state.db")
    parent = "parent_timeout"
    _seed_parent(db, parent, 4)
    # Hold lock without completing.
    assert db.try_acquire_compression_lock(parent, "stuck", ttl_seconds=30.0)

    result = wait_for_peer_compression(
        session_db=db,
        parent_session_id=parent,
        agent=SimpleNamespace(session_id=parent),
        timeout_seconds=0.4,
        poll_seconds=0.05,
    )
    assert result.status == "timeout"
    db.release_compression_lock(parent, "stuck")


def test_wait_failed_when_lock_released_without_rotation(tmp_path: Path) -> None:
    db = SessionDB(db_path=tmp_path / "state.db")
    parent = "parent_fail"
    _seed_parent(db, parent, 4)
    assert db.try_acquire_compression_lock(parent, "aborting", ttl_seconds=30.0)

    def _release_soon() -> None:
        time.sleep(0.15)
        db.release_compression_lock(parent, "aborting")

    threading.Thread(target=_release_soon, daemon=True).start()
    result = wait_for_peer_compression(
        session_db=db,
        parent_session_id=parent,
        agent=SimpleNamespace(session_id=parent),
        timeout_seconds=2.0,
        poll_seconds=0.05,
    )
    assert result.status == "failed"
    assert "lock_released" in result.detail


def test_feedback_reports_attached_winner() -> None:
    before = [{"role": "user", "content": "a"} for _ in range(10)]
    after = [
        {"role": "user", "content": "[CONTEXT COMPACTION] s"},
        {"role": "user", "content": "tail"},
    ]
    state = SimpleNamespace(
        _last_compress_aborted=False,
        _last_summary_fallback_used=False,
        _last_compress_attached_to_winner=True,
        _last_compress_skip_reason=None,
    )
    fb = summarize_manual_compression(
        before, after, 100_000, 40_000, compression_state=state
    )
    assert fb["attached_to_winner"] is True
    assert fb["noop"] is False
    assert "attached" in fb["headline"].lower()
    assert fb["reduced_tokens"] == 60_000


def test_compress_session_history_attaches_loser(monkeypatch, tmp_path: Path) -> None:
    """Loser path must adopt winner messages — never leave parent history."""
    import tui_gateway.server as server

    db = SessionDB(db_path=tmp_path / "state.db")
    parent = "sid_attach"
    child = "sid_child"
    _seed_parent(db, parent, 8)
    db.end_session(parent, end_reason="compression")
    db.create_session(session_id=child, source="test", parent_session_id=parent)
    db.append_message(child, "user", "[CONTEXT COMPACTION] done")
    db.append_message(child, "assistant", "ok")

    before = [
        {"role": "user", "content": f"m{i}"} for i in range(8)
    ]
    agent = SimpleNamespace(
        session_id=parent,
        _session_db=db,
        _cached_system_prompt="",
        tools=None,
        context_compressor=SimpleNamespace(
            _last_compress_skip_reason="concurrent_lock",
            _last_compress_aborted=False,
        ),
        _last_compress_skip_reason="concurrent_lock",
    )

    def _fake_compress(history, *_a, **_k):
        return history, ""

    agent._compress_context = _fake_compress
    session = {
        "agent": agent,
        "history": list(before),
        "history_version": 1,
        "history_lock": threading.Lock(),
        "session_key": parent,
        "session_id": parent,
    }

    monkeypatch.setattr(server, "_status_update", lambda *a, **k: None)
    monkeypatch.setattr(server, "_get_usage", lambda _a: {})

    removed, _usage = server._compress_session_history(
        session,
        None,
        approx_tokens=50_000,
        before_messages=before,
        history_version=1,
        wait_timeout_seconds=2.0,
    )
    assert removed >= 1
    assert len(session["history"]) == 2
    assert "COMPACTION" in (session["history"][0].get("content") or "")
    assert getattr(agent, "_last_compress_attached_to_winner", False) is True
