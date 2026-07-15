"""Execute a claimed ClickUp task via the dedicated Hermes Task OS profile."""

from __future__ import annotations

try:
    from agent.capability_gap import build_gap_report
    from agent.skill_discovery import propose_discovery
except Exception:  # pragma: no cover
    build_gap_report = None  # type: ignore
    propose_discovery = None  # type: ignore

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlparse

from plugins.clickup_task_os.client import ClickUpTask
from plugins.clickup_task_os.safety import requires_human_approval


_EVIDENCE_RE = re.compile(
    r"(?im)^\s*(?:evidence|artifact|artifacts|path|paths|output)\s*:\s*(.+)$"
)
_BLOCKER_RE = re.compile(r"(?im)^\s*(?:blocker|blockers|question|needed)\s*:\s*(.+)$")
_WAITING_RE = re.compile(r"(?im)^\s*status\s*:\s*waiting\b")
_REVIEW_RE = re.compile(r"(?im)^\s*status\s*:\s*review\b")
_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
# Memory/todo/session bookkeeping must never count as completion evidence.
_BOOKKEEPING_RE = re.compile(
    r"(?i)\b(mem0|memory|todo|todos|session\s*search|session\s*db|"
    r"conversation\s*history|kanban\s*status\s*only)\b"
)


def build_worker_prompt(task: ClickUpTask, cfg: Mapping[str, Any], kanban_id: str) -> str:
    models = cfg.get("models") or {}
    return f"""You are Hermes Task OS executing a ClickUp Ops task.

ClickUp ID: {task.id}
Kanban ID: {kanban_id}
URL: {task.url}
Title: {task.name}

Brief:
{task.description}

Model roles (use when helpful; primary executor is {models.get('executor')}):
- planner: {models.get('planner')}
- executor: {models.get('executor')}
- verify/classify: {models.get('verify')}
- reviewer: {models.get('reviewer')}

Hard rules:
1. Do the work using existing tools/systems. Prefer reuse over new architecture.
2. Public, destructive, financial, credential, publishing, emailing, or customer-facing
   actions MUST NOT be performed. Stop and request approval instead.
3. Never treat memory/todo/session bookkeeping as completion evidence.
4. Never claim Done. End in Review or Waiting.
5. Max two repair attempts if something fails; then Waiting with a precise question.

When finished, end your final message with exactly this machine-readable trailer:

STATUS: review|waiting
SUMMARY: <one paragraph>
EVIDENCE:
- <absolute path or URL that resolves>
BLOCKERS:
- <precise question or none>
APPROVAL_REQUIRED: yes|no
"""


def evidence_is_resolvable(item: str) -> bool:
    """Return True only for substantive, checkable evidence references.

    Accepts:
    - existing local filesystem paths
    - http(s) URLs with a non-empty host

    Rejects bookkeeping claims (memory/todo/session) and invented paths.
    """
    raw = (item or "").strip().strip("`").strip('"').strip("'")
    if not raw or _BOOKKEEPING_RE.search(raw):
        return False
    if _URL_RE.match(raw):
        parsed = urlparse(raw)
        return bool(parsed.scheme in {"http", "https"} and parsed.netloc)
    path = Path(raw).expanduser()
    try:
        return path.exists()
    except OSError:
        return False


def partition_evidence(items: Sequence[str]) -> Tuple[List[str], List[str]]:
    good: List[str] = []
    bad: List[str] = []
    for item in items:
        if evidence_is_resolvable(item):
            good.append(item)
        else:
            bad.append(item)
    return good, bad


def parse_worker_output(text: str, *, approval_required: bool = False) -> Dict[str, Any]:
    """Parse worker trailer with a deterministic completion gate.

    Independent of the core agent: prose-only or non-resolvable evidence
    cannot land as Review success. Never honors STATUS: done.
    """
    text = text or ""
    status = "review"
    if _WAITING_RE.search(text):
        status = "waiting"
    elif _REVIEW_RE.search(text):
        status = "review"

    summary = ""
    m = re.search(r"(?im)^\s*SUMMARY\s*:\s*(.+)$", text)
    if m:
        summary = m.group(1).strip()
    if not summary:
        # Fall back to last non-empty paragraph, but treat as insufficient evidence.
        paras = [p.strip() for p in text.strip().split("\n\n") if p.strip()]
        summary = paras[-1][:1200] if paras else "(empty worker output)"

    evidence = [m.group(1).strip() for m in _EVIDENCE_RE.finditer(text)]
    # Also collect bullet lines under an EVIDENCE: header
    evidence.extend(_bullets_after(text, "EVIDENCE"))
    evidence = _dedupe(evidence)
    resolvable, rejected = partition_evidence(evidence)

    blockers = [m.group(1).strip() for m in _BLOCKER_RE.finditer(text)]
    blockers.extend(_bullets_after(text, "BLOCKERS"))
    blockers = [b for b in _dedupe(blockers) if b.lower() not in ("none", "n/a", "-")]

    ar = approval_required
    if re.search(r"(?im)^\s*APPROVAL_REQUIRED\s*:\s*yes\b", text):
        ar = True

    # Deterministic completion gate (Task OS Phase 1):
    # prose-only / bookkeeping / non-resolvable paths cannot be Review success.
    if status == "review" and not ar and not resolvable:
        status = "waiting"
        if rejected:
            blockers.append(
                "Rejected non-resolvable or bookkeeping evidence: "
                + "; ".join(rejected[:5])
            )
        blockers.append(
            "Completion gate: Review requires at least one resolvable "
            "artifact path or URL. Prose-only claims are not enough."
        )

    return {
        "status": status,
        "summary": summary,
        "evidence": resolvable,
        "rejected_evidence": rejected,
        "blockers": blockers,
        "approval_required": ar,
        "attempted_done": bool(re.search(r"(?im)^\s*STATUS\s*:\s*done\b", text)),
        "raw_len": len(text),
    }


def _bullets_after(text: str, header: str) -> List[str]:
    lines = text.splitlines()
    out: List[str] = []
    capture = False
    header_re = re.compile(rf"(?i)^\s*{re.escape(header)}\s*:?\s*$")
    stop_re = re.compile(r"(?i)^\s*[A-Z][A-Z0-9_]+\s*:")
    for line in lines:
        if header_re.match(line):
            capture = True
            continue
        if capture:
            if stop_re.match(line) and not line.strip().startswith("-"):
                break
            if line.strip().startswith("-"):
                out.append(line.strip().lstrip("-").strip())
            elif not line.strip():
                continue
            else:
                # continuation or end
                if out and not line.strip().startswith("-"):
                    break
    return out


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def deterministic_smoke_worker(
    task: ClickUpTask,
    kanban_id: str,
    cfg: Mapping[str, Any],
) -> Dict[str, Any]:
    """Operator smoke executor: writes a real artifact without an LLM call."""
    path = Path(f"/tmp/hermes-task-os-smoke-{task.id}.txt")
    path.write_text(
        f"Task OS smoke OK\nclickup={task.id}\nkanban={kanban_id}\n"
        f"title={task.name}\n",
        encoding="utf-8",
    )
    return {
        "status": "review",
        "summary": f"Deterministic smoke wrote artifact for {task.name!r}.",
        "evidence": [str(path)],
        "blockers": [],
        "approval_required": False,
        "attempted_done": False,
        "profile": str(cfg.get("worker_profile") or "task-os"),
        "model": "deterministic-smoke",
    }


def run_task_os_worker(
    task: ClickUpTask,
    kanban_id: str,
    cfg: Mapping[str, Any],
    *,
    runner: Optional[Any] = None,
    deterministic: bool = False,
) -> Dict[str, Any]:
    if deterministic:
        return deterministic_smoke_worker(task, kanban_id, cfg)

    brief = f"{task.name}\n{task.description}"
    approval = requires_human_approval(brief, cfg)
    if approval:
        return {
            "status": "review",
            "summary": (
                "High-risk / approval-gated task. Hermes prepared understanding only "
                "and did not execute side effects."
            ),
            "evidence": [],
            "blockers": [
                "Explicit Dylan approval required before any public, destructive, "
                "financial, credential, publishing, emailing, or customer-facing action."
            ],
            "approval_required": True,
            "attempted_done": False,
            "skipped_execution": True,
        }

    prompt = build_worker_prompt(task, cfg, kanban_id)
    profile = str(cfg.get("worker_profile") or "task-os")
    models = cfg.get("models") or {}
    executor = str(models.get("executor") or "").strip()

    if runner is not None:
        text = runner(prompt, profile=profile, model=executor)
    else:
        text = _subprocess_hermes_chat(prompt, profile=profile, model=executor)

    parsed = parse_worker_output(text, approval_required=False)
    parsed["profile"] = profile
    parsed["model"] = executor
    # Soft-fail enrichment: when waiting/blockers suggest missing capability, attach guidance.
    if (
        propose_discovery is not None
        and str(parsed.get("status")) == "waiting"
        and (parsed.get("blockers") or [])
    ):
        try:
            discovery = propose_discovery(f"{task.name}\n{task.description}")
            parsed.setdefault("blockers", []).append(
                "skill_discovery: " + ", ".join((discovery.get("task_tags") or [])[:6])
            )
            matches = discovery.get("installed_matches") or []
            if matches:
                parsed.setdefault("evidence", []).append(f"skill_matches:{matches[:3]}")
            if build_gap_report is not None:
                gap = build_gap_report(
                    requested_outcome=task.name,
                    missing_capability="task_os_waiting_blocker",
                    alternatives_checked=list(parsed.get("blockers") or [])[:5],
                    recommended=["review installed skill matches", "escalate to Dylan"],
                    installation_risk="low",
                    engineering_required=False,
                    notes="Auto-attached from capability_gap on waiting outcome",
                )
                parsed.setdefault("evidence", []).append("capability_gap_md_present")
                parsed["capability_gap_markdown"] = gap.to_markdown()
        except Exception:  # noqa: BLE001
            pass
    return parsed


def _subprocess_hermes_chat(prompt: str, *, profile: str, model: str) -> str:
    """Invoke `hermes -p <profile> chat -q` (headless one-shot)."""
    cmd = ["hermes", "-p", profile, "chat", "-q", prompt]
    if model:
        # Best-effort model pin; ignore if CLI rejects flag in this build.
        cmd.extend(["--model", model])
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=int(60 * 45),
            check=False,
        )
    except FileNotFoundError:
        return (
            "STATUS: waiting\n"
            "SUMMARY: hermes binary not found on PATH for Task OS worker.\n"
            "EVIDENCE:\n"
            "BLOCKERS:\n- Install/link hermes for profile task-os\n"
            "APPROVAL_REQUIRED: no\n"
        )
    except subprocess.TimeoutExpired:
        return (
            "STATUS: waiting\n"
            "SUMMARY: Worker timed out.\n"
            "EVIDENCE:\n"
            "BLOCKERS:\n- Worker exceeded 45m timeout\n"
            "APPROVAL_REQUIRED: no\n"
        )

    text = (proc.stdout or "").strip()
    if proc.returncode != 0:
        err = (proc.stderr or "").strip()
        return (
            "STATUS: waiting\n"
            f"SUMMARY: Worker exited {proc.returncode}.\n"
            "EVIDENCE:\n"
            f"BLOCKERS:\n- {err[:800] if err else 'non-zero exit'}\n"
            "APPROVAL_REQUIRED: no\n"
            f"\n{text}\n"
        )
    return text or (
        "STATUS: waiting\n"
        "SUMMARY: Worker returned empty output.\n"
        "EVIDENCE:\n"
        "BLOCKERS:\n- Empty stdout from hermes chat\n"
        "APPROVAL_REQUIRED: no\n"
    )
