"""Task OS thin-wire: capability_gap + skill_discovery on failure/waiting paths."""

from __future__ import annotations

from plugins.clickup_task_os.poller import _failure_guidance
from plugins.clickup_task_os.client import ClickUpTask
from plugins.clickup_task_os.worker import run_task_os_worker


def test_failure_guidance_includes_gap_heading():
    md = _failure_guidance("Demo task", RuntimeError("boom"))
    assert "Capability gap" in md or "Poller exception" in md


def test_waiting_worker_enriches_with_discovery(monkeypatch):
    task = ClickUpTask(
        id="t9",
        name="Need calendar integration",
        description="Sync Google Calendar",
        status="next",
        tags=("hermes-ready",),
        url="https://app.clickup.com/t/t9",
        raw={"id": "t9", "list": {"id": "901524109892"}},
    )

    def fake_runner(prompt, *, profile, model):
        return "STATUS: waiting\nBLOCKER: missing calendar connector\nSUMMARY: cannot proceed"

    out = run_task_os_worker(task, "k1", {"worker_profile": "task-os", "models": {}}, runner=fake_runner)
    assert out["status"] == "waiting"
    assert any(str(b).startswith("skill_discovery:") for b in out.get("blockers") or [])
