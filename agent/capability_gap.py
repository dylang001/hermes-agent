"""Structured capability-gap reports when Hermes cannot complete a task.

Not a new registry — a typed report builders used by workers / chat when an
integration is missing or unhealthy. Safe to call from plugins and skills.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class CapabilityGapReport:
    requested_outcome: str
    missing_capability: str
    alternatives_checked: list[str] = field(default_factory=list)
    recommended: list[str] = field(default_factory=list)  # plugin / MCP / skill ids
    installation_risk: str = "unknown"  # low | medium | high
    engineering_required: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        alts = "\n".join(f"- {a}" for a in self.alternatives_checked) or "- (none)"
        recs = "\n".join(f"- {r}" for r in self.recommended) or "- (none)"
        eng = "yes" if self.engineering_required else "no"
        return (
            "## Capability gap\n\n"
            f"**Requested outcome:** {self.requested_outcome}\n\n"
            f"**Missing capability:** {self.missing_capability}\n\n"
            f"**Alternatives checked:**\n{alts}\n\n"
            f"**Recommended plugin/MCP/skill:**\n{recs}\n\n"
            f"**Installation risk:** {self.installation_risk}\n\n"
            f"**Engineering-agent work required:** {eng}\n\n"
            f"{self.notes}".rstrip()
            + "\n"
        )


def build_gap_report(
    *,
    requested_outcome: str,
    missing_capability: str,
    alternatives_checked: list[str] | None = None,
    recommended: list[str] | None = None,
    installation_risk: str = "medium",
    engineering_required: bool = False,
    notes: str = "",
) -> CapabilityGapReport:
    return CapabilityGapReport(
        requested_outcome=requested_outcome,
        missing_capability=missing_capability,
        alternatives_checked=list(alternatives_checked or []),
        recommended=list(recommended or []),
        installation_risk=installation_risk,
        engineering_required=engineering_required,
        notes=notes,
    )
