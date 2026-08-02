"""CE Observatory dashboard API — read-only JSONL aggregation.

Mounted at ``/api/plugins/ce_observatory/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Query

# Plugin package root (…/plugins/ce_observatory)
_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from aggregator import build_summary  # noqa: E402

router = APIRouter()


@router.get("/summary")
def summary(
    max_lines: int = Query(
        default=0,
        ge=0,
        le=500_000,
        description="If >0, only the last N lines of each JSONL are read.",
    ),
):
    """Return live aggregates from HERMES_HOME/logs CE JSONL streams."""
    return build_summary(max_lines=max_lines or None)


@router.get("/health")
def health():
    return {"ok": True, "plugin": "ce_observatory", "mode": "observation"}
