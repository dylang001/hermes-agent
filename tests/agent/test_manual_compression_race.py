"""Race / attach-to-winner coverage for manual /compress.

Determinism rules (do not regress):
- Contended lock tests use a threading.Barrier in front of
  ``try_acquire_compression_lock`` — never rely on ``time.sleep`` inside the
  compressor to create overlap (CI starvation lets one path finish + release
  before the other reaches acquire).
- Threads must be joined with an assert they are dead before reading skip
  flags / child counts (``join(timeout=…)`` alone is not a completion barrier).
"""

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


def _build_agent(db: SessionDB, sid: str, *, hold_event: threading.Event | None = None):
    import os
    from unittest.mock import patch

    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
        from run_agent import AIAgent

        agent = AIAgent(
            api_key="test-key",
            base_url="https://openrouter.ai/api/v1",
            model="test/model",
            quiet_mode=True,
            session_db=db,
            session_id=sid,
            skip_context_files=True,
            skip_memory=True,
        )

    def _compress(*_a, **_k):
        if hold_event is not None:
            # Deterministic hold: wait until test releases, not wall-clock sleep.
            assert hold_event.wait(timeout=15), "compress hold_event timed out"
        return [
            {"role": "user", "content": "[CONTEXT COMPACTION] summary"},
            {"role": "user", "content": "tail"},
        ]

    compressor = MagicMock()
    compressor.compress.side_effect = _compress
    compressor.compression_count = 1
    compressor.last_prompt_tokens = 0
    compressor.last_completion_tokens = 0
    compressor._last_summary_error = None
    compressor._last_compress_aborted = False
    agent.context_compressor = compressor
    agent.compression_in_place = False
    return agent


def _join_alive(threads: list[threading.Thread], timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    for t in threads:
        remaining = max(0.1, deadline - time.monotonic())
        t.join(timeout=remaining)
    alive = [t.name for t in threads if t.is_alive()]
    assert not alive, f"threads still alive after {timeout}s: {alive}"


def test_force_true_still_serializes_on_compression_lock(tmp_path: Path) -> None:
    """force=True bypasses cooldown only — two compressors must not both rotate.

    Proven flake (2026-07-22): prior version used ``time.sleep(0.3)`` +
    ``join(timeout=10)`` without asserting thread death. Under load the loser
    had not yet written ``_last_compress_skip_reason``, so the assertion saw
    ``[None, None]`` while a single child already existed::

        AssertionError: assert ('concurrent_lock' in [None, None]
                                or 'already_rotated' in [None, None])
    """
    db = SessionDB(db_path=tmp_path / "state.db")
    parent = "parent_force_lock"
    _seed_parent(db, parent, 10)

    hold = threading.Event()
    agents = [
        _build_agent(db, parent, hold_event=hold),
        _build_agent(db, parent, hold_event=hold),
    ]

    barrier = threading.Barrier(2, timeout=15)
    real_acquire = db.try_acquire_compression_lock

    def _barriered_acquire(*args, **kwargs):
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass
        return real_acquire(*args, **kwargs)

    db.try_acquire_compression_lock = _barriered_acquire  # type: ignore[method-assign]

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

    threads = [
        threading.Thread(target=_run, args=(0,), name="compress-a"),
        threading.Thread(target=_run, args=(1,), name="compress-b"),
    ]
    for t in threads:
        t.start()

    # Release the winner's compress hold once both threads have contended for
    # the lock. Poll for the winner entering compress() without a fixed sleep
    # that could expire before either thread is scheduled.
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if any(
            getattr(a.context_compressor.compress, "call_count", 0) > 0
            for a in agents
        ):
            break
        time.sleep(0.01)
    hold.set()
    _join_alive(threads, timeout=30.0)
    db.try_acquire_compression_lock = real_acquire  # type: ignore[method-assign]

    assert not errors
    assert all(r is not None for r in results)

    children = db._conn.execute(
        "SELECT id FROM sessions WHERE parent_session_id = ?", (parent,)
    ).fetchall()
    assert len(children) == 1, f"expected exactly one child, got {children}"

    skip_flags = [getattr(a, "_last_compress_skip_reason", None) for a in agents]
    assert "concurrent_lock" in skip_flags or "already_rotated" in skip_flags, (
        f"expected lock-loser skip reason, got {skip_flags!r}"
    )

    rotated = sum(1 for a in agents if a.session_id != parent)
    assert rotated == 1, f"expected exactly one rotation, got {rotated}"


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
    # Messages must come from the persisted child tip, not an in-memory stub.
    persisted = db.get_messages_as_conversation(child)
    assert result.messages == persisted


def test_wait_timeout_when_peer_never_finishes(tmp_path: Path) -> None:
    db = SessionDB(db_path=tmp_path / "state.db")
    parent = "parent_timeout"
    _seed_parent(db, parent, 4)
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

    # Release after the waiter has started with assume_lock_held — no sleep race
    # on first-poll observing the lock.
    start = threading.Event()
    released = threading.Event()

    def _release_after_start() -> None:
        assert start.wait(timeout=5)
        db.release_compression_lock(parent, "aborting")
        released.set()

    threading.Thread(target=_release_after_start, daemon=True).start()
    start.set()
    result = wait_for_peer_compression(
        session_db=db,
        parent_session_id=parent,
        agent=SimpleNamespace(session_id=parent),
        timeout_seconds=2.0,
        poll_seconds=0.05,
        assume_lock_held=True,
    )
    assert released.wait(timeout=2)
    assert result.status == "failed"
    assert "lock_released" in result.detail


def test_crashed_winner_lock_expires_and_is_reclaimable(tmp_path: Path) -> None:
    """TTL reclaim: a crashed holder cannot leave a permanent lock."""
    db = SessionDB(db_path=tmp_path / "state.db")
    parent = "parent_ttl"
    _seed_parent(db, parent, 4)
    assert db.try_acquire_compression_lock(parent, "crashed", ttl_seconds=0.15)
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if db.get_compression_lock_holder(parent) is None:
            break
        time.sleep(0.05)
    assert db.get_compression_lock_holder(parent) is None
    assert db.try_acquire_compression_lock(parent, "fresh") is True
    db.release_compression_lock(parent, "fresh")


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


def test_feedback_compression_still_running_not_noop() -> None:
    before = [{"role": "user", "content": "x"} for _ in range(6)]
    state = SimpleNamespace(
        _last_compress_aborted=False,
        _last_summary_fallback_used=False,
        _last_compress_attached_to_winner=False,
        _last_compress_skip_reason="compression_still_running",
    )
    fb = summarize_manual_compression(
        before, before, 50_000, 50_000, compression_state=state
    )
    assert fb["noop"] is True  # messages unchanged
    assert fb["skip_reason"] == "compression_still_running"
    assert "still running" in fb["headline"].lower() or "in progress" in (
        fb.get("note") or ""
    ).lower() or "in-flight" in (fb.get("note") or "").lower()


def test_compress_session_history_attaches_loser(monkeypatch, tmp_path: Path) -> None:
    """Loser adopts winner's persisted tip; history_version is tip-invalidation only."""
    import tui_gateway.server as server

    db = SessionDB(db_path=tmp_path / "state.db")
    parent = "sid_attach"
    child = "sid_child"
    _seed_parent(db, parent, 8)
    db.end_session(parent, end_reason="compression")
    db.create_session(session_id=child, source="test", parent_session_id=parent)
    db.append_message(child, "user", "[CONTEXT COMPACTION] done")
    db.append_message(child, "assistant", "ok")
    persisted = db.get_messages_as_conversation(child)

    before = [{"role": "user", "content": f"m{i}"} for i in range(8)]
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

    agent._compress_context = lambda history, *_a, **_k: (history, "")
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
    assert session["history"] == persisted
    assert getattr(agent, "_last_compress_attached_to_winner", False) is True
    # Tip-invalidation bump is allowed after adopt; waiters must not have
    # performed a CAS write against the pre-wait history_version.
    assert session["history_version"] == 2


def test_timeout_does_not_mutate_history_or_version(monkeypatch, tmp_path: Path) -> None:
    import tui_gateway.server as server

    db = SessionDB(db_path=tmp_path / "state.db")
    parent = "sid_timeout"
    _seed_parent(db, parent, 8)
    assert db.try_acquire_compression_lock(parent, "peer", ttl_seconds=60.0)

    before = [{"role": "user", "content": f"m{i}"} for i in range(8)]
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
    agent._compress_context = lambda history, *_a, **_k: (history, "")
    session = {
        "agent": agent,
        "history": list(before),
        "history_version": 7,
        "history_lock": threading.Lock(),
        "session_key": parent,
        "session_id": parent,
    }
    monkeypatch.setattr(server, "_status_update", lambda *a, **k: None)
    monkeypatch.setattr(server, "_get_usage", lambda _a: {})

    removed, _ = server._compress_session_history(
        session,
        None,
        approx_tokens=50_000,
        before_messages=before,
        history_version=7,
        wait_timeout_seconds=0.35,
    )
    assert removed == 0
    assert session["history"] == before
    assert session["history_version"] == 7
    assert getattr(agent, "_last_compress_skip_reason", None) == (
        "compression_still_running"
    )
    db.release_compression_lock(parent, "peer")


def test_later_request_retrieves_completed_child_after_timeout(
    monkeypatch, tmp_path: Path
) -> None:
    """After a wait timeout, a subsequent /compress attaches to the finished tip."""
    import tui_gateway.server as server

    db = SessionDB(db_path=tmp_path / "state.db")
    parent = "sid_later"
    child = "sid_later_child"
    _seed_parent(db, parent, 8)
    before = [{"role": "user", "content": f"m{i}"} for i in range(8)]

    # First call: lock held → timeout, no mutation.
    assert db.try_acquire_compression_lock(parent, "peer", ttl_seconds=60.0)
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
    agent._compress_context = lambda history, *_a, **_k: (history, "")
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
    removed, _ = server._compress_session_history(
        session,
        None,
        approx_tokens=50_000,
        before_messages=before,
        history_version=1,
        wait_timeout_seconds=0.3,
    )
    assert removed == 0
    assert session["history_version"] == 1

    # Peer finishes: release lock + persist child tip.
    db.release_compression_lock(parent, "peer")
    db.end_session(parent, end_reason="compression")
    db.create_session(session_id=child, source="test", parent_session_id=parent)
    db.append_message(child, "user", "[CONTEXT COMPACTION] late")
    db.append_message(child, "assistant", "done")
    persisted = db.get_messages_as_conversation(child)

    agent._last_compress_skip_reason = "already_rotated"
    agent.context_compressor._last_compress_skip_reason = "already_rotated"
    removed2, _ = server._compress_session_history(
        session,
        None,
        approx_tokens=50_000,
        before_messages=list(session["history"]),
        history_version=session["history_version"],
        wait_timeout_seconds=2.0,
    )
    assert removed2 >= 1
    assert session["history"] == persisted


def test_db_lock_serializes_across_separate_SessionDB_handles(tmp_path: Path) -> None:
    """Lock is SQLite-backed — two SessionDB handles on the same file contend.

    This is the multi-process / multi-gateway-handle guarantee: the lock is
    not process-local.
    """
    db_path = tmp_path / "shared.db"
    db_a = SessionDB(db_path=db_path)
    db_b = SessionDB(db_path=db_path)
    sid = "shared_sid"
    db_a.create_session(session_id=sid, source="test")

    assert db_a.try_acquire_compression_lock(sid, "proc-a", ttl_seconds=30.0)
    assert db_b.try_acquire_compression_lock(sid, "proc-b", ttl_seconds=30.0) is False
    assert db_b.get_compression_lock_holder(sid) == "proc-a"
    db_a.release_compression_lock(sid, "proc-a")
    assert db_b.try_acquire_compression_lock(sid, "proc-b", ttl_seconds=30.0)
    db_b.release_compression_lock(sid, "proc-b")
