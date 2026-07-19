"""Execution Coordinator — stable interface + Invariant 5 contracts."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from agent.execution_coordinator import (
    ExecutionCoordinator,
    get_execution_coordinator,
)
from agent.execution_plan import (
    BatchClass,
    ExecutionOp,
    ExecutionPlan,
    ExecutionPolicy,
    classify_tool,
    execution_plan_from_tool_calls,
)


def _tool_call(name: str, call_id: str = "c1", arguments: str = "{}"):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _assistant(tool_calls):
    return SimpleNamespace(tool_calls=tool_calls, content=None)


def _agent_with_fake_runtime(results_by_id: dict[str, tuple[str, str]]):
    """Agent whose sequential/concurrent paths append fixed tool messages."""

    agent = SimpleNamespace(
        _executing_tools=False,
        _tool_guardrail_halt_decision=None,
        _execution_coordinator=None,
    )

    def _append_results(assistant_message, messages, *_a, **_k):
        # Simulate out-of-order completion for concurrent: reverse append,
        # then coordinator must still surface plan emission order.
        calls = list(assistant_message.tool_calls)
        for tc in reversed(calls):
            name, content = results_by_id[tc.id]
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": name,
                    "content": content,
                }
            )

    agent._execute_tool_calls_sequential = MagicMock(side_effect=_append_results)
    agent._execute_tool_calls_concurrent = MagicMock(side_effect=_append_results)
    return agent


class TestStableExecuteInterface:
    def test_execute_accepts_plan_and_policy(self):
        results = {
            "a": ("read_file", "AAA"),
            "b": ("read_file", "BBB"),
        }
        agent = _agent_with_fake_runtime(results)
        coord = ExecutionCoordinator(agent)
        plan = ExecutionPlan(
            ops=[
                ExecutionOp(op_id="a", tool="read_file", arguments={"path": "a.py"}),
                ExecutionOp(op_id="b", tool="read_file", arguments={"path": "b.py"}),
            ]
        )
        messages: list = []
        result = coord.execute(
            plan,
            ExecutionPolicy.sequential(),
            messages=messages,
            effective_task_id="t1",
        )
        assert result.planner_visible.fingerprint() == (
            ("a", "read_file", "AAA"),
            ("b", "read_file", "BBB"),
        )
        assert result.stats.policy_mode == "sequential"

    def test_invariant5_sequential_equals_parallel_planner_visible(self):
        """Acceptance: planner cannot tell whether batching/parallel happened."""
        results = {
            "a": ("read_file", "content-a"),
            "b": ("search_files", "hits"),
            "c": ("web_search", "docs"),
        }
        agent = _agent_with_fake_runtime(results)
        coord = ExecutionCoordinator(agent)
        plan = ExecutionPlan(
            ops=[
                ExecutionOp(op_id="a", tool="read_file"),
                ExecutionOp(op_id="b", tool="search_files"),
                ExecutionOp(op_id="c", tool="web_search"),
            ]
        )

        msgs_seq: list = []
        r_seq = coord.execute(
            plan,
            ExecutionPolicy.sequential(),
            messages=msgs_seq,
            effective_task_id="t1",
        )

        msgs_par: list = []
        r_par = coord.execute(
            plan,
            ExecutionPolicy.parallel(),
            messages=msgs_par,
            effective_task_id="t1",
        )

        assert r_seq.planner_visible.fingerprint() == r_par.planner_visible.fingerprint()
        # Policies may differ in dispatch telemetry — that is fine / expected.
        assert r_seq.stats.dispatch == "sequential"
        assert r_par.stats.dispatch == "concurrent"
        assert r_seq.stats.policy_mode == "sequential"
        assert r_par.stats.policy_mode == "parallel"

    def test_execute_tool_calls_bridge_uses_execute(self):
        results = {"c1": ("read_file", "ok")}
        agent = _agent_with_fake_runtime(results)
        coord = ExecutionCoordinator(agent)
        msg = _assistant([_tool_call("read_file", "c1")])
        messages: list = []
        result = coord.execute_tool_calls(msg, messages, "t1", api_call_count=2)
        assert result.planner_visible.fingerprint() == (("c1", "read_file", "ok"),)
        agent._execute_tool_calls_sequential.assert_called_once()


class TestPlannerIsolation:
    def test_coordinator_has_no_prompt_cache_api(self):
        coord = ExecutionCoordinator(SimpleNamespace())
        assert not hasattr(coord, "enable_cache")
        assert not hasattr(coord, "set_cache_mode")
        assert not hasattr(coord, "prompt_cache_capability")

    def test_get_execution_coordinator_attaches_once(self):
        agent = SimpleNamespace(_execution_coordinator=None)
        a = get_execution_coordinator(agent)
        b = get_execution_coordinator(agent)
        assert a is b


class TestExecutionPlanTypes:
    def test_classify_tools(self):
        assert classify_tool("read_file") is BatchClass.SAFE
        assert classify_tool("web_search") is BatchClass.LOOKUP
        assert classify_tool("terminal") is BatchClass.MUTATING
        assert classify_tool("write_file") is BatchClass.MUTATING

    def test_plan_from_tool_calls(self):
        plan = execution_plan_from_tool_calls(
            [
                _tool_call("read_file", "x", '{"path":"a.py"}'),
                _tool_call("terminal", "y", '{"command":"ls"}'),
            ]
        )
        assert len(plan) == 2
        assert plan.ops[0].batch_class is BatchClass.SAFE
        assert plan.ops[1].batch_class is BatchClass.MUTATING
        assert plan.ops[0].group == "filesystem"

    def test_cancel_skips_runtime(self):
        agent = _agent_with_fake_runtime({})
        coord = ExecutionCoordinator(agent)
        coord.request_cancel("test")
        plan = ExecutionPlan(ops=[ExecutionOp(op_id="a", tool="read_file")])
        result = coord.execute(
            plan, ExecutionPolicy.auto(), messages=[], effective_task_id="t"
        )
        agent._execute_tool_calls_sequential.assert_not_called()
        assert result.stats.cancelled is True
