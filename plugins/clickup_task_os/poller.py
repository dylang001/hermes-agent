"""Phase 1 cron poller: Ready+hermes-ready → claim → Kanban → execute → Review/Waiting."""

from __future__ import annotations

import json
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional

from plugins.clickup_task_os.client import ClickUpClient, ClickUpTask
from plugins.clickup_task_os.config import (
    clickup_idempotency_key,
    load_task_os_config,
    resolve_api_token,
    status_name,
    tag_name,
)
from plugins.clickup_task_os.eligibility import is_dispatch_eligible
from plugins.clickup_task_os.safety import detect_high_risk


@dataclass
class PollResult:
    scanned: int = 0
    eligible: int = 0
    claimed: int = 0
    skipped: List[str] = field(default_factory=list)
    outcomes: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hermes_marker(text: str) -> str:
    return f"[Hermes Task OS · {_utc_now()}]\n{text}"


class TaskOsPoller:
    def __init__(
        self,
        *,
        client: ClickUpClient,
        cfg: Mapping[str, Any],
        create_or_get: Callable[..., tuple],
        count_active: Callable[[], int],
        run_worker: Callable[[ClickUpTask, str, Mapping[str, Any]], Dict[str, Any]],
        dry_run: bool = False,
    ):
        self.client = client
        self.cfg = cfg
        self.create_or_get = create_or_get
        self.count_active = count_active
        self.run_worker = run_worker
        self.dry_run = dry_run

    def poll(self) -> PollResult:
        result = PollResult()
        list_id = str(self.cfg["list_id"])
        ready = status_name(self.cfg, "ready")
        max_concurrent = int(self.cfg.get("max_concurrent") or 2)

        tasks = self.client.list_tasks(list_id, statuses=[ready], include_closed=False)
        result.scanned = len(tasks)

        active = self.count_active()
        slots = max(0, max_concurrent - active)
        if slots == 0:
            result.skipped.append(f"at_concurrency_cap:{active}/{max_concurrent}")
            return result

        for task in tasks:
            first = is_dispatch_eligible(task, self.cfg, require_list_id=list_id)
            if not first.eligible:
                result.skipped.append(f"{task.id}:{first.reason}")
                continue
            result.eligible += 1
            if result.claimed >= slots:
                result.skipped.append(f"{task.id}:no_slot")
                continue
            try:
                outcome = self._claim_and_run(task)
                result.outcomes.append(outcome)
                if outcome.get("claimed"):
                    result.claimed += 1
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"{task.id}:{exc}")
                traceback.print_exc()
        return result

    def _claim_and_run(self, preview: ClickUpTask) -> Dict[str, Any]:
        list_id = str(self.cfg["list_id"])
        # Second safety check immediately before claiming.
        fresh = self.client.get_task(preview.id)
        second = is_dispatch_eligible(fresh, self.cfg, require_list_id=list_id)
        if not second.eligible:
            return {
                "task_id": preview.id,
                "claimed": False,
                "reason": f"preclaim_failed:{second.reason}",
            }

        idem = clickup_idempotency_key(fresh.id)
        worker_profile = str(self.cfg.get("worker_profile") or "task-os")
        body = self._kanban_body(fresh)

        if self.dry_run:
            return {
                "task_id": fresh.id,
                "claimed": False,
                "dry_run": True,
                "idempotency_key": idem,
                "would_assign": worker_profile,
            }

        kanban_id, created_new = self.create_or_get(
            title=f"[ClickUp] {fresh.name}".strip(),
            body=body,
            assignee=worker_profile,
            idempotency_key=idem,
            max_retries=int(self.cfg.get("max_repair_attempts") or 2),
            tenant="clickup-orchidea-ops",
        )

        if not created_new:
            # Restarting the poller must not duplicate the run.
            return {
                "task_id": fresh.id,
                "claimed": False,
                "reason": "idempotent_existing",
                "kanban_id": kanban_id,
                "idempotency_key": idem,
            }

        plan = self._build_plan(fresh)
        self.client.add_comment(fresh.id, _hermes_marker(plan))
        self.client.set_status(fresh.id, status_name(self.cfg, "in_progress"))
        self.client.remove_tag(fresh.id, tag_name(self.cfg, "hermes_ready"))

        worker_out = self.run_worker(fresh, kanban_id, self.cfg)
        self._apply_terminal_state(fresh.id, worker_out)
        return {
            "task_id": fresh.id,
            "claimed": True,
            "kanban_id": kanban_id,
            "idempotency_key": idem,
            "worker": worker_out,
        }

    def _kanban_body(self, task: ClickUpTask) -> str:
        models = self.cfg.get("models") or {}
        return (
            f"ClickUp task: {task.id}\n"
            f"URL: {task.url}\n"
            f"Title: {task.name}\n\n"
            f"{task.description}\n\n"
            f"Models: planner={models.get('planner')} "
            f"executor={models.get('executor')} "
            f"verify={models.get('verify')} "
            f"reviewer={models.get('reviewer')}\n"
            "Rules: attach evidence; never mark Done from prose alone; "
            "public/destructive/financial/publish/email actions stop for approval.\n"
        )

    def _build_plan(self, task: ClickUpTask) -> str:
        risks = detect_high_risk(f"{task.name}\n{task.description}", self.cfg)
        risk_line = (
            "High-risk markers detected — will stop in Review for approval before side effects:\n"
            + "\n".join(f"- {r}" for r in risks)
            if risks
            else "No high-risk markers in brief (still enforcing approval wall for public actions)."
        )
        models = self.cfg.get("models") or {}
        return (
            "Understanding & execution plan\n"
            f"Task: {task.name}\n"
            f"ClickUp ID: {task.id}\n\n"
            "1. Re-read brief and constraints.\n"
            "2. Retrieve only relevant context (narrow).\n"
            f"3. Execute via dedicated profile with executor model `{models.get('executor')}`.\n"
            "4. Attach evidence/artifacts; do not treat chat prose as completion.\n"
            "5. Move to Review (waiting + hermes-review) or Waiting with a precise question.\n\n"
            f"{risk_line}"
        )

    def _apply_terminal_state(self, task_id: str, worker_out: Mapping[str, Any]) -> None:
        status = str(worker_out.get("status") or "review")
        summary = str(worker_out.get("summary") or "").strip() or "(no summary)"
        evidence = worker_out.get("evidence") or []
        blockers = worker_out.get("blockers") or []
        comment = "Result\n" + summary
        if evidence:
            comment += "\n\nEvidence:\n" + "\n".join(f"- {e}" for e in evidence)
        if blockers:
            comment += "\n\nBlockers:\n" + "\n".join(f"- {b}" for b in blockers)
        if worker_out.get("approval_required"):
            comment += "\n\nAPPROVAL REQUIRED — no public/side-effect action was taken."
            self.client.ensure_tags(task_id, [tag_name(self.cfg, "approval_required")])

        self.client.add_comment(task_id, _hermes_marker(comment))

        if status == "waiting":
            self.client.set_status(task_id, status_name(self.cfg, "waiting"))
            self.client.ensure_tags(task_id, [tag_name(self.cfg, "waiting_on_dylan")])
            return

        # Review mapping: status waiting + hermes-review tag (no native Review column yet).
        self.client.set_status(task_id, status_name(self.cfg, "review"))
        self.client.ensure_tags(task_id, [tag_name(self.cfg, "hermes_review")])
        if worker_out.get("attempted_done"):
            self.client.add_comment(
                task_id,
                _hermes_marker(
                    "Blocked automatic Done. Phase 1 always lands in Review for human close."
                ),
            )


def build_poller(
    *,
    dry_run: bool = False,
    deterministic_worker: bool = False,
    cfg: Optional[Mapping[str, Any]] = None,
    client: Optional[ClickUpClient] = None,
) -> TaskOsPoller:
    from plugins.clickup_task_os.kanban_bridge import (
        count_active_clickup_tasks,
        create_or_get_task,
    )
    from plugins.clickup_task_os.worker import run_task_os_worker

    config = dict(cfg or load_task_os_config())
    click_client = client or ClickUpClient(resolve_api_token())

    def _worker(task, kanban_id, cfg_inner):
        return run_task_os_worker(
            task,
            kanban_id,
            cfg_inner,
            deterministic=deterministic_worker,
        )

    return TaskOsPoller(
        client=click_client,
        cfg=config,
        create_or_get=create_or_get_task,
        count_active=count_active_clickup_tasks,
        run_worker=_worker,
        dry_run=dry_run,
    )


def poll_once(*, dry_run: bool = False, deterministic_worker: bool = False) -> PollResult:
    return build_poller(
        dry_run=dry_run,
        deterministic_worker=deterministic_worker,
    ).poll()


def format_poll_result(result: PollResult) -> str:
    payload = {
        "scanned": result.scanned,
        "eligible": result.eligible,
        "claimed": result.claimed,
        "skipped": result.skipped[:20],
        "outcomes": result.outcomes,
        "errors": result.errors,
    }
    return json.dumps(payload, indent=2)
