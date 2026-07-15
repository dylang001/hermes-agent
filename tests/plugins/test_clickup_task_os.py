"""Phase 1 tests for ClickUp Task OS plugin (no live network)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from plugins.clickup_task_os.client import ClickUpTask
from plugins.clickup_task_os.config import (
    clickup_idempotency_key,
    load_task_os_config,
    status_name,
    tag_name,
)
from plugins.clickup_task_os.eligibility import is_dispatch_eligible
from plugins.clickup_task_os.poller import TaskOsPoller
from plugins.clickup_task_os.safety import detect_high_risk, requires_human_approval
from plugins.clickup_task_os.worker import parse_worker_output


def _task(
    *,
    task_id: str = "t1",
    name: str = "Do a thing",
    description: str = "Write a note",
    status: str = "next",
    tags: List[str] | None = None,
    list_id: str = "901524109892",
) -> ClickUpTask:
    return ClickUpTask(
        id=task_id,
        name=name,
        description=description,
        status=status,
        tags=tuple(["hermes-ready"] if tags is None else tags),
        url=f"https://app.clickup.com/t/{task_id}",
        raw={"id": task_id, "list": {"id": list_id}},
    )


@pytest.fixture
def cfg() -> Dict[str, Any]:
    return load_task_os_config()


def test_defaults_map_ops_ready_to_next(cfg):
    assert cfg["list_id"] == "901524109892"
    assert status_name(cfg, "ready") == "next"
    assert status_name(cfg, "in_progress") == "in-progress"
    assert status_name(cfg, "review") == "waiting"
    assert tag_name(cfg, "hermes_ready") == "hermes-ready"
    assert tag_name(cfg, "hermes_review") == "hermes-review"


def test_idempotency_key_format():
    assert clickup_idempotency_key("86abc") == "clickup:86abc"


def test_eligible_only_when_ready_and_tagged(cfg):
    ok = is_dispatch_eligible(_task(), cfg)
    assert ok.eligible

    bad_status = is_dispatch_eligible(_task(status="inbox"), cfg)
    assert not bad_status.eligible
    assert "status_not_ready" in bad_status.reason

    bad_tag = is_dispatch_eligible(_task(tags=[]), cfg)
    assert not bad_tag.eligible
    assert bad_tag.reason == "missing_hermes_ready_tag"

    wrong_list = is_dispatch_eligible(_task(list_id="other"), cfg, require_list_id="901524109892")
    assert not wrong_list.eligible


def test_high_risk_gate():
    assert requires_human_approval("Please send email to the customer tomorrow")
    assert detect_high_risk("publish the landing page now")
    assert not requires_human_approval("Draft an internal outline in Obsidian")


def test_parse_worker_output_never_done_from_prose():
    parsed = parse_worker_output("I finished everything successfully.")
    assert parsed["status"] == "waiting"
    assert any("completion gate" in b.lower() or "evidence" in b.lower() for b in parsed["blockers"])


def test_parse_worker_output_rejects_bookkeeping_and_fake_paths(tmp_path: Path):
    text = f"""
STATUS: review
SUMMARY: Remembered it in mem0 and marked a todo.
EVIDENCE:
- mem0:updated preferences
- /definitely/not/real/path-{tmp_path.name}.md
BLOCKERS:
- none
APPROVAL_REQUIRED: no
"""
    parsed = parse_worker_output(text)
    assert parsed["status"] == "waiting"
    assert parsed["evidence"] == []
    assert parsed["rejected_evidence"]


def test_parse_worker_output_review_with_resolvable_evidence(tmp_path: Path):
    artifact = tmp_path / "out.md"
    artifact.write_text("ok\n", encoding="utf-8")
    text = f"""
STATUS: review
SUMMARY: Wrote the brief.
EVIDENCE:
- {artifact}
BLOCKERS:
- none
APPROVAL_REQUIRED: no
"""
    parsed = parse_worker_output(text)
    assert parsed["status"] == "review"
    assert str(artifact) in parsed["evidence"]
    assert parsed["attempted_done"] is False


def test_parse_blocks_attempted_done_flag(tmp_path: Path):
    artifact = tmp_path / "x"
    artifact.write_text("x\n", encoding="utf-8")
    text = f"STATUS: done\nSUMMARY: nope\nEVIDENCE:\n- {artifact}\n"
    parsed = parse_worker_output(text)
    assert parsed["attempted_done"] is True
    # STATUS done is not honored as Done; evidence can still yield Review.
    assert parsed["status"] == "review"


class _FakeClient:
    def __init__(self, tasks: List[ClickUpTask]):
        self._tasks = {t.id: t for t in tasks}
        self.comments: List[tuple[str, str]] = []
        self.statuses: List[tuple[str, str]] = []
        self.removed_tags: List[tuple[str, str]] = []
        self.ensured_tags: List[tuple[str, List[str]]] = []

    def list_tasks(self, list_id, *, statuses=None, include_closed=False, page=0):
        ready = (statuses or [None])[0]
        out = []
        for t in self._tasks.values():
            if ready is None or t.status_matches(ready):
                out.append(t)
        return out

    def get_task(self, task_id: str) -> ClickUpTask:
        return self._tasks[task_id]

    def add_comment(self, task_id: str, text: str):
        self.comments.append((task_id, text))
        return {}

    def set_status(self, task_id: str, status: str):
        t = self._tasks[task_id]
        self.statuses.append((task_id, status))
        updated = ClickUpTask(
            id=t.id,
            name=t.name,
            description=t.description,
            status=status,
            tags=t.tags,
            url=t.url,
            raw=t.raw,
        )
        self._tasks[task_id] = updated
        return updated

    def remove_tag(self, task_id: str, tag: str):
        t = self._tasks[task_id]
        self.removed_tags.append((task_id, tag))
        self._tasks[task_id] = ClickUpTask(
            id=t.id,
            name=t.name,
            description=t.description,
            status=t.status,
            tags=tuple(x for x in t.tags if x.casefold() != tag.casefold()),
            url=t.url,
            raw=t.raw,
        )

    def ensure_tags(self, task_id: str, tags):
        self.ensured_tags.append((task_id, list(tags)))
        t = self._tasks[task_id]
        merged = tuple(dict.fromkeys(list(t.tags) + list(tags)))
        self._tasks[task_id] = ClickUpTask(
            id=t.id,
            name=t.name,
            description=t.description,
            status=t.status,
            tags=merged,
            url=t.url,
            raw=t.raw,
        )


def test_poller_claims_once_and_moves_to_review_mapping(cfg):
    client = _FakeClient([_task(task_id="86a")])
    creates: List[str] = []

    def create_or_get(**kwargs):
        creates.append(kwargs["idempotency_key"])
        # First call creates; subsequent with same key are existing
        if len(creates) == 1:
            return "k1", True
        return "k1", False

    def run_worker(task, kanban_id, _cfg):
        return {
            "status": "review",
            "summary": "Done the research note",
            "evidence": ["/tmp/hermes-task-os-unit-evidence.md"],
            "blockers": [],
            "approval_required": False,
            "attempted_done": False,
        }

    poller = TaskOsPoller(
        client=client,
        cfg=cfg,
        create_or_get=create_or_get,
        count_active=lambda: 0,
        run_worker=run_worker,
    )
    first = poller.poll()
    assert first.claimed == 1
    assert creates == ["clickup:86a"]
    assert any("Understanding" in c[1] for c in client.comments)
    assert ("86a", "in-progress") in client.statuses
    assert ("86a", "hermes-ready") in client.removed_tags
    # Review mapping
    assert ("86a", "waiting") in client.statuses
    assert any("hermes-review" in tags for _, tags in client.ensured_tags)

    # Restart poller — task no longer Ready; nothing claimed.
    # Simulate ClickUp left in waiting after first run:
    second = poller.poll()
    assert second.claimed == 0


def test_poller_idempotent_skip_does_not_rerun(cfg):
    client = _FakeClient([_task(task_id="86b")])
    runs = {"n": 0}

    def create_or_get(**kwargs):
        return "k-existing", False

    def run_worker(*_a, **_k):
        runs["n"] += 1
        return {"status": "review", "summary": "x", "evidence": ["/t"], "blockers": []}

    poller = TaskOsPoller(
        client=client,
        cfg=cfg,
        create_or_get=create_or_get,
        count_active=lambda: 0,
        run_worker=run_worker,
    )
    out = poller.poll()
    assert out.claimed == 0
    assert out.outcomes[0]["reason"] == "idempotent_existing"
    assert runs["n"] == 0
    assert client.statuses == []


def test_poller_skips_non_eligible(cfg):
    client = _FakeClient(
        [
            _task(task_id="inbox1", status="inbox"),
            _task(task_id="notag", tags=[]),
        ]
    )
    poller = TaskOsPoller(
        client=client,
        cfg=cfg,
        create_or_get=lambda **k: ("k", True),
        count_active=lambda: 0,
        run_worker=lambda *a, **k: {},
    )
    out = poller.poll()
    assert out.claimed == 0
    assert out.eligible == 0


def test_preclaim_safety_check(cfg):
    """Second check fails if task changes between list and claim."""
    mutable = _task(task_id="race")

    class FlipClient(_FakeClient):
        def get_task(self, task_id: str) -> ClickUpTask:
            # Appears Ready in list_tasks, but get_task shows inbox
            return _task(task_id=task_id, status="inbox")

    client = FlipClient([mutable])
    poller = TaskOsPoller(
        client=client,
        cfg=cfg,
        create_or_get=lambda **k: ("k", True),
        count_active=lambda: 0,
        run_worker=lambda *a, **k: {"status": "review", "summary": "x", "evidence": ["/e"]},
    )
    out = poller.poll()
    assert out.claimed == 0
    assert "preclaim_failed" in out.outcomes[0]["reason"]


def test_high_risk_worker_skips_execution(cfg):
    from plugins.clickup_task_os.worker import run_task_os_worker

    task = _task(name="Publish blog post", description="publish to LinkedIn now")
    called = {"n": 0}

    def runner(prompt, profile=None, model=None):
        called["n"] += 1
        return "STATUS: review\nSUMMARY: should not run\nEVIDENCE:\n- /x\n"

    out = run_task_os_worker(task, "k1", cfg, runner=runner)
    assert out["approval_required"] is True
    assert out.get("skipped_execution") is True
    assert called["n"] == 0


def test_config_overlay(tmp_path: Path):
    (tmp_path / "clickup_task_os.yaml").write_text(
        "max_concurrent: 1\nlist_id: '999'\n",
        encoding="utf-8",
    )
    # Still needs full required keys from defaults merge — overlay only overrides
    cfg = load_task_os_config(hermes_home=tmp_path)
    assert cfg["max_concurrent"] == 1
    assert cfg["list_id"] == "999"
    assert cfg["workspace_id"] == "90152507264"
