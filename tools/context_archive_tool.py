"""Context Engineering V2 — ``context_archive`` retrieve tool (P6).

Service-gated: only appears when ``context_engineering_v2.retrieve.enabled``
is true. Lets the model list/get SAFE archive entries with budgeted raw
segments. Also enqueues a pending inject for the next assemble (Layer 5
tail append).
"""

from __future__ import annotations

import json
from typing import Any, Optional

from tools.registry import registry, tool_error


def check_context_archive_requirements() -> bool:
    try:
        from agent.context_engineering_v2 import retrieve_enabled

        return bool(retrieve_enabled())
    except Exception:
        return False


def _session_db():
    try:
        from hermes_state import SessionDB

        return SessionDB()
    except Exception:
        return None


def context_archive_tool(
    action: str = "list",
    archive_id: Optional[str] = None,
    max_tokens: Optional[int] = None,
    offset_chars: int = 0,
    session_id: Optional[str] = None,
) -> str:
    from agent.context_engineering_v2 import (
        _DEFAULT_RETRIEVE_MAX_TOKENS,
        _load_retrieve_config,
        enqueue_pending_retrieve,
        get_archive_raw,
        list_archive_summaries,
    )

    sid = (session_id or "").strip()
    if not sid:
        return tool_error("session_id required for context_archive", success=False)

    db = _session_db()
    if db is None:
        return tool_error("session database unavailable", success=False)

    cfg = _load_retrieve_config()
    budget = int(max_tokens or cfg.get("max_tokens") or _DEFAULT_RETRIEVE_MAX_TOKENS)
    act = (action or "list").strip().lower()

    if act == "list":
        items = list_archive_summaries(sid, session_db=db, limit=50)
        return json.dumps(
            {
                "success": True,
                "action": "list",
                "count": len(items),
                "archives": items,
            },
            ensure_ascii=False,
        )

    if act == "get":
        if not archive_id:
            return tool_error("archive_id required for action=get", success=False)
        payload = get_archive_raw(
            sid,
            str(archive_id),
            session_db=db,
            max_tokens=budget,
            offset_chars=int(offset_chars or 0),
        )
        if not payload.get("ok"):
            return tool_error(payload.get("error") or "retrieve failed", success=False)
        enqueue_pending_retrieve(
            sid,
            str(archive_id),
            session_db=db,
            reason="tool_get",
            max_tokens=budget,
        )
        return json.dumps(
            {
                "success": True,
                "action": "get",
                "archive_id": payload.get("archive_id"),
                "summary": payload.get("summary"),
                "content": payload.get("content"),
                "truncated": payload.get("truncated"),
                "tokens_est": payload.get("tokens_est"),
                "offset_chars": payload.get("offset_chars"),
                "next_offset": payload.get("next_offset"),
                "total_chars": payload.get("total_chars"),
                "queued_for_next_assemble": True,
                "hint": (
                    "Pass offset_chars=next_offset to page further. "
                    "Raw dump is also queued to append on the next API call."
                ),
            },
            ensure_ascii=False,
        )

    return tool_error(f"unknown action: {action}", success=False)


CONTEXT_ARCHIVE_SCHEMA = {
    "name": "context_archive",
    "description": (
        "List or retrieve archived SAFE tool dumps from this session's "
        "context archive (Layer 5). Use when a summary says "
        "[archived:tr_…] and you need the raw evidence. Pagination via "
        "offset_chars is allowed for large dumps."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "get"],
                "description": "list archive index, or get one archive_id",
            },
            "archive_id": {
                "type": "string",
                "description": "Archive id (e.g. tr_abc12345) for action=get",
            },
            "max_tokens": {
                "type": "integer",
                "description": "Max tokens of raw content to return (default ~4000)",
            },
            "offset_chars": {
                "type": "integer",
                "description": "Byte/char offset into the raw blob for paging",
            },
        },
        "required": ["action"],
    },
}


registry.register(
    name="context_archive",
    toolset="context_archive",
    schema=CONTEXT_ARCHIVE_SCHEMA,
    handler=lambda args, **kw: context_archive_tool(
        action=str(args.get("action") or "list"),
        archive_id=args.get("archive_id"),
        max_tokens=args.get("max_tokens"),
        offset_chars=int(args.get("offset_chars") or 0),
        session_id=kw.get("session_id"),
    ),
    check_fn=check_context_archive_requirements,
    emoji="📦",
)
