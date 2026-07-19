"""Execution Plan types — Planner output shape for the Execution Coordinator.

Milestone 2 contract (see ``audit/HERMES_TRACK_B_PLAN.md``):

* The planner emits an :class:`ExecutionPlan` (today: adapted from OpenAI
  tool_calls; later: native structured plans).
* The Coordinator decides batch / parallel / sequence / retry / cancel.
* :class:`PlannerVisibleResult` is identical regardless of
  :class:`ExecutionPolicy` (Invariant 5).

This module is pure data + classification. No I/O. No LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class BatchClass(str, Enum):
    """Whether an op may be batched / parallelised under the Coordinator."""

    SAFE = "safe"  # file reads, grep, metadata, stat
    LOOKUP = "lookup"  # independent HTTP / API reads
    MUTATING = "mutating"  # writes, shell mutations — ordered by default


class ExecutionMode(str, Enum):
    """How the Coordinator schedules a plan (planner-invisible)."""

    AUTO = "auto"  # adaptive: batch independent SAFE/LOOKUP; order MUTATING
    SEQUENTIAL = "sequential"  # force total order (correctness / debug)
    PARALLEL = "parallel"  # force concurrent where class allows


# Tool → batch class. Unknown tools default to MUTATING (correctness first).
_SAFE_TOOLS = frozenset(
    {
        "ha_get_state",
        "ha_list_entities",
        "ha_list_services",
        "read_file",
        "search_files",
        "session_search",
        "skill_view",
        "skills_list",
        "vision_analyze",
    }
)
_LOOKUP_TOOLS = frozenset(
    {
        "web_extract",
        "web_search",
    }
)


def classify_tool(tool_name: str) -> BatchClass:
    name = (tool_name or "").strip()
    if name in _SAFE_TOOLS:
        return BatchClass.SAFE
    if name in _LOOKUP_TOOLS:
        return BatchClass.LOOKUP
    return BatchClass.MUTATING


def advisory_group(tool_name: str) -> str:
    """Optional grouping hint for plan authors / telemetry (not a schedule)."""
    name = (tool_name or "").strip()
    if name in {"read_file", "search_files", "write_file", "patch"}:
        return "filesystem"
    if name in {"web_search", "web_extract"}:
        return "search"
    if name in {"terminal", "execute_code"}:
        return "shell"
    return "other"


@dataclass(frozen=True)
class ExecutionOp:
    """One atomic operation in an execution plan."""

    op_id: str
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    group: str = ""
    batch_class: Optional[BatchClass] = None

    def __post_init__(self) -> None:
        if not self.group:
            object.__setattr__(self, "group", advisory_group(self.tool))
        if self.batch_class is None:
            object.__setattr__(self, "batch_class", classify_tool(self.tool))


@dataclass
class ExecutionPlan:
    """Planner output: what to run. Never how."""

    ops: list[ExecutionOp] = field(default_factory=list)
    turn_id: Optional[str] = None

    def __len__(self) -> int:
        return len(self.ops)


@dataclass(frozen=True)
class ExecutionPolicy:
    """Coordinator-only knobs. The planner must never set these."""

    mode: ExecutionMode = ExecutionMode.AUTO

    @staticmethod
    def auto() -> "ExecutionPolicy":
        return ExecutionPolicy(mode=ExecutionMode.AUTO)

    @staticmethod
    def sequential() -> "ExecutionPolicy":
        return ExecutionPolicy(mode=ExecutionMode.SEQUENTIAL)

    @staticmethod
    def parallel() -> "ExecutionPolicy":
        return ExecutionPolicy(mode=ExecutionMode.PARALLEL)


@dataclass(frozen=True)
class PlannerVisibleItem:
    """One tool result as the planner must see it."""

    op_id: str
    tool: str
    content: str


@dataclass
class PlannerVisibleResult:
    """Consolidated result object for the planner.

    Acceptance criterion: identical for the same plan under any
    :class:`ExecutionPolicy` (Invariant 5).
    """

    items: list[PlannerVisibleItem] = field(default_factory=list)

    def fingerprint(self) -> tuple[tuple[str, str, str], ...]:
        """Stable comparison key — ignores stats / timing / dispatch."""
        return tuple((i.op_id, i.tool, i.content) for i in self.items)

    def to_tool_messages(self) -> list[dict[str, Any]]:
        """OpenAI-wire tool messages in emission order."""
        return [
            {
                "role": "tool",
                "tool_call_id": item.op_id,
                "name": item.tool,
                "content": item.content,
            }
            for item in self.items
        ]


def execution_plan_from_tool_calls(tool_calls: Any) -> ExecutionPlan:
    """Adapt today's OpenAI-style tool_calls into an ExecutionPlan."""
    import json

    ops: list[ExecutionOp] = []
    for tc in tool_calls or []:
        fn = getattr(tc, "function", None) or (
            tc.get("function") if isinstance(tc, dict) else None
        )
        if fn is None:
            continue
        name = getattr(fn, "name", None) or (
            fn.get("name") if isinstance(fn, dict) else ""
        )
        raw_args = getattr(fn, "arguments", None) or (
            fn.get("arguments") if isinstance(fn, dict) else {}
        )
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args) if raw_args.strip() else {}
            except (json.JSONDecodeError, TypeError):
                args = {"_raw": raw_args}
        elif isinstance(raw_args, dict):
            args = raw_args
        else:
            args = {}
        op_id = (
            getattr(tc, "id", None)
            or (tc.get("id") if isinstance(tc, dict) else None)
            or f"op_{len(ops)}"
        )
        tool = str(name or "")
        ops.append(
            ExecutionOp(
                op_id=str(op_id),
                tool=tool,
                arguments=args if isinstance(args, dict) else {},
            )
        )
    return ExecutionPlan(ops=ops)


def assistant_message_from_plan(plan: ExecutionPlan) -> Any:
    """Build a minimal assistant message for the legacy tool_executor path."""
    from types import SimpleNamespace

    tool_calls = []
    for op in plan.ops:
        import json

        tool_calls.append(
            SimpleNamespace(
                id=op.op_id,
                type="function",
                function=SimpleNamespace(
                    name=op.tool,
                    arguments=json.dumps(op.arguments or {}),
                ),
            )
        )
    return SimpleNamespace(tool_calls=tool_calls, content=None)
