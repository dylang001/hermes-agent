"""Staged skill discovery on top of the existing skills hub (no second loader).

Workflow:
1. classify task (caller-supplied tags)
2. search installed skills
3. search approved hub catalogs
4. evaluate candidate (static checklist)
5. quarantine via skills_hub
6. require approval for code/credential/external-write skills
7. enable only for a named profile when approved
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


APPROVED_CATALOGS = (
    "official",  # hermes optional-skills / official source
)


@dataclass
class SkillEvaluation:
    name: str
    source: str
    source_reputation: str  # official | approved_tap | unknown | untrusted
    permissions: list[str] = field(default_factory=list)
    has_scripts: bool = False
    dependencies: list[str] = field(default_factory=list)
    secret_access: bool = False
    prompt_injection_risk: str = "unknown"  # low | medium | high
    maintenance_status: str = "unknown"
    requires_approval: bool = True
    checksum: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_task_tags(text: str) -> list[str]:
    """Tiny heuristic classifier — callers may replace with LLM labels."""
    lower = (text or "").lower()
    tags: list[str] = []
    mapping = {
        "engineering": ("git", "pr", "pytest", "refactor", "bug", "code"),
        "research": ("research", "summarize", "sources", "web search"),
        "content": ("newsletter", "blog", "copy", "voice", "orchidea"),
        "prospecting": ("prospect", "outreach", "apollo", "lead", "signal"),
        "browser": ("browser", "screenshot", "click", "navigate"),
        "admin": ("cron", "plugin", "mcp", "install", "gateway"),
    }
    for tag, needles in mapping.items():
        if any(n in lower for n in needles):
            tags.append(tag)
    return tags or ["general"]


def search_installed_skills(query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """Search skills already on disk via the built-in skills index."""
    try:
        from tools.skills_tool import _find_all_skills
    except Exception:
        return []

    q = (query or "").lower().strip()
    results: list[dict[str, Any]] = []
    for skill in _find_all_skills() or []:
        name = str(skill.get("name") or "")
        desc = str(skill.get("description") or "")
        blob = f"{name} {desc}".lower()
        if not q or q in blob:
            results.append({"name": name, "description": desc, "source": "installed"})
        if len(results) >= limit:
            break
    return results


def evaluate_skill_dir(skill_dir: Path, *, source: str = "unknown") -> SkillEvaluation:
    """Static evaluation before enable — never auto-enables."""
    skill_md = skill_dir / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8") if skill_md.is_file() else ""
    scripts = list(skill_dir.glob("scripts/**/*")) if (skill_dir / "scripts").is_dir() else []
    lower = text.lower()
    secret_access = any(k in lower for k in ("api_key", "token", "password", "credential", ".env"))
    external_write = any(k in lower for k in ("send email", "publish", "post to", "clickup", "telegram"))
    permissions: list[str] = []
    if scripts:
        permissions.append("execute_scripts")
    if secret_access:
        permissions.append("secret_access")
    if external_write:
        permissions.append("external_write")
    if "terminal" in lower or "```bash" in lower:
        permissions.append("shell_guidance")

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""
    reputation = "official" if source in APPROVED_CATALOGS else (
        "approved_tap" if source.startswith("tap:") else "unknown"
    )
    if reputation == "unknown" and "github.com" in source:
        reputation = "untrusted"

    requires_approval = bool(
        scripts or secret_access or external_write or reputation in {"unknown", "untrusted"}
    )
    injection = "high" if "{{" in text or "ignore previous" in lower else (
        "medium" if len(text) > 15_000 else "low"
    )

    return SkillEvaluation(
        name=skill_dir.name,
        source=source,
        source_reputation=reputation,
        permissions=permissions,
        has_scripts=bool(scripts),
        dependencies=[],
        secret_access=secret_access,
        prompt_injection_risk=injection,
        maintenance_status="unknown",
        requires_approval=requires_approval,
        checksum=digest,
        notes="Static evaluation only — run sandbox checks before enable.",
    )


def propose_discovery(task: str) -> dict[str, Any]:
    """End-to-end proposal object for chat / Task OS comments."""
    tags = classify_task_tags(task)
    installed = search_installed_skills(task, limit=8)
    return {
        "task_tags": tags,
        "installed_matches": installed,
        "next_steps": [
            "If an installed skill matches, load it with skills_list / skill tools.",
            "If none match, search approved catalogs only (hermes skills / hub).",
            "Quarantine → static eval → sandbox → human approval before enable.",
            "Never auto-install from untrusted GitHub URLs.",
        ],
        "approval_required_for": [
            "execute_scripts",
            "secret_access",
            "external_write",
            "modify_hermes",
        ],
    }
