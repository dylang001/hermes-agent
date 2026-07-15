"""Deterministic Ready + hermes-ready eligibility checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

from plugins.clickup_task_os.client import ClickUpTask
from plugins.clickup_task_os.config import status_name, tag_name


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    reason: str


def is_dispatch_eligible(
    task: ClickUpTask,
    cfg: Mapping,
    *,
    require_list_id: Optional[str] = None,
) -> EligibilityResult:
    """Return whether Hermes may begin work on this ClickUp task.

    Trigger (both required):
      status == configured Ready status (Ops: ``next``)
      AND tag == hermes-ready
    """
    ready = status_name(cfg, "ready")
    hermes_ready = tag_name(cfg, "hermes_ready")
    list_id = require_list_id or str(cfg.get("list_id") or "")

    raw_list = ""
    raw = task.raw or {}
    if isinstance(raw.get("list"), dict):
        raw_list = str(raw["list"].get("id") or "")
    if list_id and raw_list and raw_list != list_id:
        return EligibilityResult(False, f"wrong_list:{raw_list}")

    if not task.status_matches(ready):
        return EligibilityResult(False, f"status_not_ready:{task.status}")

    if not task.has_tag(hermes_ready):
        return EligibilityResult(False, "missing_hermes_ready_tag")

    if task.has_tag(tag_name(cfg, "hermes_review")):
        return EligibilityResult(False, "already_in_review_tag")

    return EligibilityResult(True, "ok")
