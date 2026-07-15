"""Kanban helpers for ClickUp Task OS (idempotency_key=clickup:<id>)."""

from __future__ import annotations

from typing import Any, Optional, Tuple


BOARD = "task-os"


def create_or_get_task(
    *,
    title: str,
    body: str,
    assignee: str,
    idempotency_key: str,
    max_retries: int = 2,
    tenant: str = "clickup-orchidea-ops",
    board: str = BOARD,
) -> Tuple[str, bool]:
    """Return (task_id, created_new).

    created_new is False when an existing non-archived task matched the key.
    """
    from hermes_cli import kanban_db

    conn = kanban_db.connect(board=board)
    try:
        existing = None
        row = conn.execute(
            "SELECT id FROM tasks WHERE idempotency_key = ? "
            "AND status != 'archived' LIMIT 1",
            (idempotency_key,),
        ).fetchone()
        if row:
            existing = str(row[0])

        task_id = kanban_db.create_task(
            conn,
            title=title,
            body=body,
            assignee=assignee,
            idempotency_key=idempotency_key,
            max_retries=max_retries,
            tenant=tenant,
            board=board,
        )
        created_new = existing is None
        return str(task_id), created_new
    finally:
        conn.close()


def count_active_clickup_tasks(board: str = BOARD) -> int:
    from hermes_cli import kanban_db

    conn = kanban_db.connect(board=board)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM tasks "
            "WHERE status IN ('ready','running','todo','triage') "
            "AND idempotency_key LIKE 'clickup:%'"
        ).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def mark_kanban_complete(
    task_id: str,
    *,
    summary: str,
    board: str = BOARD,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """Best-effort complete; ignore if APIs differ by version."""
    from hermes_cli import kanban_db

    conn = kanban_db.connect(board=board)
    try:
        if hasattr(kanban_db, "complete_task"):
            kanban_db.complete_task(
                conn,
                task_id,
                summary=summary,
                metadata=metadata or {},
            )
        else:
            conn.execute(
                "UPDATE tasks SET status='done' WHERE id=?",
                (task_id,),
            )
            conn.commit()
    except Exception:
        # Non-fatal for ClickUp-facing flow.
        pass
    finally:
        conn.close()
