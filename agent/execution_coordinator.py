"""Execution Coordinator — permanent thin waist between Planner and Runtime.

Track B (see ``audit/HERMES_TRACK_B_PLAN.md``).

Stable public API (do not break):

    coordinator.execute(plan, policy) -> ExecutionResult

* ``plan``     — what the planner wants (ExecutionPlan)
* ``policy``   — how the runtime may schedule (ExecutionPolicy; planner-invisible)
* ``result.planner_visible`` — identical for the same plan under any policy
  (Invariant 5)

Milestone 1: pass-through dispatch via legacy tool_executor.
Milestone 2: adaptive batching behind this interface — planner cannot tell.

Architectural rules:

1. Planner owns reasoning. Runtime owns execution.
2. Workers are disposable.
3. The runtime may batch; the planner must not know.
4. Prompt stability is sacred (append-only tool results).
5. Execution results are deterministic regardless of batching strategy.

Prompt-cache capability is **not** this layer (Track A, frozen).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agent.execution_plan import (
    ExecutionMode,
    ExecutionPlan,
    ExecutionPolicy,
    PlannerVisibleItem,
    PlannerVisibleResult,
    assistant_message_from_plan,
    execution_plan_from_tool_calls,
)


@dataclass
class ExecutionBatchStats:
    """Runtime telemetry — never shown as planner content."""

    tool_call_count: int = 0
    segment_count: int = 0
    dispatch: str = ""  # sequential | concurrent | segmented
    policy_mode: str = ""
    cancelled: bool = False
    halted: bool = False


@dataclass
class ExecutionResult:
    """Coordinator outcome.

    ``planner_visible`` is the only field the planner / message loop should
    treat as semantic. ``stats`` is for KPIs and debugging.
    """

    planner_visible: PlannerVisibleResult = field(
        default_factory=PlannerVisibleResult
    )
    stats: ExecutionBatchStats = field(default_factory=ExecutionBatchStats)


class ExecutionCoordinator:
    """Schedules an ExecutionPlan; returns a consolidated planner result."""

    def __init__(self, agent: Any) -> None:
        self._agent = agent
        self._cancel_requested = False
        self.last_stats: ExecutionBatchStats = ExecutionBatchStats()
        self.last_result: Optional[ExecutionResult] = None

    # ── Stable API ─────────────────────────────────────────────────

    def execute(
        self,
        plan: ExecutionPlan,
        policy: Optional[ExecutionPolicy] = None,
        *,
        messages: list,
        effective_task_id: str,
        api_call_count: int = 0,
        assistant_message: Any = None,
    ) -> ExecutionResult:
        """Run ``plan`` under ``policy``; append tool results to ``messages``.

        Acceptance: for a fixed plan, ``result.planner_visible.fingerprint()``
        must not depend on ``policy.mode``.
        """
        policy = policy or ExecutionPolicy.auto()
        stats = ExecutionBatchStats(
            tool_call_count=len(plan.ops),
            policy_mode=policy.mode.value,
        )

        if self._cancel_requested:
            stats.cancelled = True
            result = ExecutionResult(stats=stats)
            self.last_stats = stats
            self.last_result = result
            return result

        if not plan.ops:
            result = ExecutionResult(stats=stats)
            self.last_stats = stats
            self.last_result = result
            return result

        msg = assistant_message or assistant_message_from_plan(plan)
        start_len = len(messages)

        agent = self._agent
        agent._executing_tools = True
        try:
            self._dispatch(msg, messages, effective_task_id, api_call_count, policy, stats)
        finally:
            agent._executing_tools = False

        if getattr(agent, "_tool_guardrail_halt_decision", None) is not None:
            stats.halted = True

        visible = self._planner_visible_from_messages(
            messages, start_len=start_len, plan=plan
        )
        result = ExecutionResult(planner_visible=visible, stats=stats)
        self.last_stats = stats
        self.last_result = result
        return result

    def execute_tool_calls(
        self,
        assistant_message: Any,
        messages: list,
        effective_task_id: str,
        api_call_count: int = 0,
        policy: Optional[ExecutionPolicy] = None,
    ) -> ExecutionResult:
        """Bridge: OpenAI tool_calls → ExecutionPlan → :meth:`execute`.

        Kept for ``AIAgent._execute_tool_calls`` / conversation_loop until
        the planner emits ExecutionPlan natively.
        """
        plan = execution_plan_from_tool_calls(
            getattr(assistant_message, "tool_calls", None)
        )
        return self.execute(
            plan,
            policy,
            messages=messages,
            effective_task_id=effective_task_id,
            api_call_count=api_call_count,
            assistant_message=assistant_message,
        )

    # ── Cancel ─────────────────────────────────────────────────────

    def request_cancel(self, reason: str = "user interrupt") -> None:
        """Soft cancel flag (Milestone 1). Full interrupt lands with budgets."""
        self._cancel_requested = True
        self.last_stats = ExecutionBatchStats(
            cancelled=True,
            dispatch=self.last_stats.dispatch,
            tool_call_count=self.last_stats.tool_call_count,
            segment_count=self.last_stats.segment_count,
            policy_mode=self.last_stats.policy_mode,
        )
        _ = reason

    def clear_cancel(self) -> None:
        self._cancel_requested = False

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_requested

    # ── Internals ──────────────────────────────────────────────────

    def _dispatch(
        self,
        assistant_message: Any,
        messages: list,
        effective_task_id: str,
        api_call_count: int,
        policy: ExecutionPolicy,
        stats: ExecutionBatchStats,
    ) -> None:
        agent = self._agent
        tool_calls = assistant_message.tool_calls

        if policy.mode is ExecutionMode.SEQUENTIAL or len(tool_calls) <= 1:
            stats.dispatch = "sequential"
            stats.segment_count = 1
            agent._execute_tool_calls_sequential(
                assistant_message, messages, effective_task_id, api_call_count
            )
            return

        if policy.mode is ExecutionMode.PARALLEL:
            # Parallel where the legacy path allows; otherwise sequential.
            # Never widens mutating ops beyond existing safety checks —
            # concurrent executor still applies its own guards.
            stats.dispatch = "concurrent"
            stats.segment_count = 1
            agent._execute_tool_calls_concurrent(
                assistant_message, messages, effective_task_id, api_call_count
            )
            return

        # AUTO — existing adaptive segment planner
        from agent.tool_dispatch_helpers import _plan_tool_batch_segments

        segments = _plan_tool_batch_segments(tool_calls)
        stats.segment_count = len(segments)

        if len(segments) == 1:
            kind = segments[0][0]
            if kind == "parallel":
                stats.dispatch = "concurrent"
                agent._execute_tool_calls_concurrent(
                    assistant_message, messages, effective_task_id, api_call_count
                )
            else:
                stats.dispatch = "sequential"
                agent._execute_tool_calls_sequential(
                    assistant_message, messages, effective_task_id, api_call_count
                )
            return

        stats.dispatch = "segmented"
        from agent.tool_executor import execute_tool_calls_segmented

        execute_tool_calls_segmented(
            agent,
            assistant_message,
            messages,
            effective_task_id,
            api_call_count,
            segments=segments,
        )

    @staticmethod
    def _planner_visible_from_messages(
        messages: list,
        *,
        start_len: int,
        plan: ExecutionPlan,
    ) -> PlannerVisibleResult:
        """Collect tool results in plan emission order (not completion order)."""
        by_id: dict[str, PlannerVisibleItem] = {}
        for msg in messages[start_len:]:
            if not isinstance(msg, dict) or msg.get("role") != "tool":
                continue
            op_id = str(msg.get("tool_call_id") or "")
            if not op_id:
                continue
            by_id[op_id] = PlannerVisibleItem(
                op_id=op_id,
                tool=str(msg.get("name") or ""),
                content=str(msg.get("content") or ""),
            )
        items = []
        for op in plan.ops:
            if op.op_id in by_id:
                items.append(by_id[op.op_id])
            else:
                # Missing result — still emit a stable placeholder so
                # fingerprints stay comparable across policies.
                items.append(
                    PlannerVisibleItem(
                        op_id=op.op_id, tool=op.tool, content=""
                    )
                )
        return PlannerVisibleResult(items=items)


def get_execution_coordinator(agent: Any) -> ExecutionCoordinator:
    """Return the agent's coordinator, creating one if absent."""
    coord = getattr(agent, "_execution_coordinator", None)
    if isinstance(coord, ExecutionCoordinator):
        return coord
    coord = ExecutionCoordinator(agent)
    try:
        agent._execution_coordinator = coord
    except Exception:
        pass
    return coord
