"""Wait for / attach to an in-flight peer compression (manual /compress).

When two manual ``/compress`` calls race, only the lock holder may rotate the
session. Losers must NOT rewrite history with an unchanged snapshot — they
wait for the winner and adopt its tip so the UI reports real before/after
numbers.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional, Sequence

logger = logging.getLogger(__name__)

# Manual summarisation on large sessions routinely takes 1–3 minutes.
_DEFAULT_WAIT_SECONDS = 180.0
_DEFAULT_POLL_SECONDS = 0.5


@dataclass
class PeerCompressionWaitResult:
    """Outcome of waiting for another path's compression to finish."""

    status: str  # completed | timeout | failed | not_needed
    messages: Optional[list] = None
    session_id: Optional[str] = None
    parent_session_id: Optional[str] = None
    detail: str = ""


def find_compression_child_session_id(session_db: Any, parent_session_id: str) -> Optional[str]:
    """Return the newest compression-continuation child of ``parent_session_id``."""
    if session_db is None or not parent_session_id:
        return None
    try:
        rows = session_db._conn.execute(
            """
            SELECT id FROM sessions
            WHERE parent_session_id = ?
            ORDER BY started_at DESC
            LIMIT 8
            """,
            (parent_session_id,),
        ).fetchall()
    except Exception as exc:
        logger.debug("find_compression_child failed: %s", exc)
        return None
    for row in rows:
        child_id = row["id"] if hasattr(row, "keys") else row[0]
        try:
            child = session_db.get_session(child_id)
        except Exception:
            child = None
        if not child:
            continue
        is_child = getattr(session_db, "_is_compression_child_row", None)
        if callable(is_child):
            try:
                if not is_child(child):
                    continue
            except Exception:
                continue
        else:
            try:
                parent = session_db.get_session(parent_session_id) or {}
            except Exception:
                parent = {}
            if parent.get("end_reason") != "compression":
                continue
        return str(child_id)
    return None


def load_session_messages(session_db: Any, session_id: str) -> list:
    """Load conversation messages for a session tip (empty on failure)."""
    if session_db is None or not session_id:
        return []
    try:
        getter = getattr(session_db, "get_messages_as_conversation", None)
        if callable(getter):
            msgs = getter(session_id)
            if isinstance(msgs, list):
                return list(msgs)
    except Exception as exc:
        logger.debug("get_messages_as_conversation failed: %s", exc)
    try:
        rows = session_db.get_messages(session_id)
    except Exception as exc:
        logger.debug("get_messages failed: %s", exc)
        return []
    out: list = []
    for row in rows or []:
        if isinstance(row, dict):
            out.append(dict(row))
        else:
            try:
                out.append(dict(row))
            except Exception:
                continue
    return out


def compression_lock_held(session_db: Any, session_id: str) -> bool:
    if session_db is None or not session_id:
        return False
    try:
        holder = session_db.get_compression_lock_holder(session_id)
    except Exception:
        return False
    return bool(holder)


def wait_for_peer_compression(
    *,
    session_db: Any,
    parent_session_id: str,
    agent: Any = None,
    timeout_seconds: float = _DEFAULT_WAIT_SECONDS,
    poll_seconds: float = _DEFAULT_POLL_SECONDS,
    before_message_count: Optional[int] = None,
    assume_lock_held: bool = False,
) -> PeerCompressionWaitResult:
    """Block until a peer compressor finishes, then return its tip messages.

    Polls for:
    1. Parent ``end_reason == compression`` + child tip with messages
    2. Agent ``session_id`` rotation away from the parent (in-process winner)
    3. Lock release without rotation (winner aborted) → ``failed``

    ``assume_lock_held``: set True when the caller already observed
    ``concurrent_lock`` / an active holder. Avoids a race where the lock is
    released before the first poll, which would otherwise time out instead of
    reporting ``failed`` / completing via the child tip.
    """
    parent_session_id = str(parent_session_id or "")
    if not parent_session_id or session_db is None:
        return PeerCompressionWaitResult(
            status="not_needed", detail="no session_db/parent"
        )

    deadline = time.monotonic() + max(1.0, float(timeout_seconds))
    poll = max(0.05, float(poll_seconds))
    saw_lock = bool(assume_lock_held) or compression_lock_held(
        session_db, parent_session_id
    )

    while time.monotonic() < deadline:
        # In-process winner already rotated this agent.
        if agent is not None:
            live_sid = str(getattr(agent, "session_id", "") or "")
            if live_sid and live_sid != parent_session_id:
                msgs = load_session_messages(session_db, live_sid)
                if msgs and (
                    before_message_count is None
                    or len(msgs) != before_message_count
                    or True  # rotation alone is enough
                ):
                    return PeerCompressionWaitResult(
                        status="completed",
                        messages=msgs,
                        session_id=live_sid,
                        parent_session_id=parent_session_id,
                        detail="agent_session_id_rotated",
                    )

        child_id = find_compression_child_session_id(session_db, parent_session_id)
        if child_id:
            msgs = load_session_messages(session_db, child_id)
            if msgs:
                return PeerCompressionWaitResult(
                    status="completed",
                    messages=msgs,
                    session_id=child_id,
                    parent_session_id=parent_session_id,
                    detail="compression_child_ready",
                )

        lock_held = compression_lock_held(session_db, parent_session_id)
        if saw_lock and not lock_held and not child_id:
            # Winner released without producing a child — aborted / failed.
            try:
                parent = session_db.get_session(parent_session_id) or {}
            except Exception:
                parent = {}
            if parent.get("end_reason") == "compression":
                # Child not visible yet; keep polling briefly.
                pass
            else:
                return PeerCompressionWaitResult(
                    status="failed",
                    parent_session_id=parent_session_id,
                    detail="lock_released_without_rotation",
                )
        if lock_held:
            saw_lock = True

        time.sleep(poll)

    return PeerCompressionWaitResult(
        status="timeout",
        parent_session_id=parent_session_id,
        detail=f"waited_{timeout_seconds:.0f}s",
    )


def mark_agent_attached_to_winner(
    agent: Any,
    *,
    winner_session_id: str,
    messages: Sequence[dict],
) -> None:
    """Update agent skip markers after adopting a peer compression tip."""
    if agent is None:
        return
    try:
        agent._last_compress_skip_reason = None
        agent._last_compress_attached_to_winner = True
        agent._last_compress_winner_session_id = winner_session_id
    except Exception:
        pass
    cc = getattr(agent, "context_compressor", None)
    if cc is not None:
        try:
            cc._last_compress_skip_reason = None
            cc._last_compress_attached_to_winner = True
        except Exception:
            pass
    try:
        agent.session_id = winner_session_id
    except Exception:
        pass
