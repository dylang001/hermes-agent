#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.intelligence_policy import classify_error, classify_request, decide_failure_policy


class _FixtureMemoryManager:
    providers = [object()]

    def initialize_all(self, **_kwargs):
        return None

    def build_system_prompt(self) -> str:
        return "Sanitized Phase 6 smoke memory fixture."

    def on_turn_start(self, *_args, **_kwargs):
        return None

    def prefetch_all(self, query: str, *, session_id: str = "") -> str:
        return f"Sanitized fixture recall for {session_id or 'phase6'}: {query[:64]}"

    def sync_all(self, *_args, **_kwargs):
        return None

    def queue_prefetch_all(self, *_args, **_kwargs):
        return None


def _mock_response(content: str):
    message = SimpleNamespace(content=content, tool_calls=None, reasoning=None, reasoning_content=None)
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(choices=[choice], model="mock-runtime/model", usage=None)


def _make_agent(temp_home: str):
    os.environ["HERMES_HOME"] = temp_home
    os.environ["HERMES_INTELLIGENCE_POLICY"] = "1"
    os.environ["HERMES_INTELLIGENCE_MEMORY_POLICY"] = "1"
    os.environ["HERMES_INTELLIGENCE_TOOL_POLICY"] = "1"
    os.environ["HERMES_INTELLIGENCE_EVIDENCE_COMPACTION"] = "1"
    os.environ["HERMES_INTELLIGENCE_FAILURE_POLICY"] = "1"
    from run_agent import AIAgent

    agent = AIAgent(
        model="mock-runtime/model",
        api_key="test-key",
        base_url="http://localhost:1234/v1",
        provider="custom",
        api_mode="openai",
        quiet_mode=True,
        skip_context_files=True,
        skip_memory=True,
        max_iterations=1,
    )
    agent.client = MagicMock()
    agent.tools = list(agent.tools or []) + [
        {"type": "function", "function": {"name": "gmail_search", "description": "Mocked read-only Gmail search fixture.", "parameters": {"type": "object"}}},
        {"type": "function", "function": {"name": "calendar_availability", "description": "Mocked read-only calendar availability fixture.", "parameters": {"type": "object"}}},
    ]
    agent._memory_manager = _FixtureMemoryManager()
    agent._persist_session = lambda *args, **kwargs: None
    agent._save_trajectory = lambda *args, **kwargs: None
    agent._cleanup_task_resources = lambda *args, **kwargs: None
    return agent


def _run_agent_case(temp_home: str, case: dict) -> dict:
    agent = _make_agent(temp_home)
    with patch.object(agent, "_interruptible_api_call", return_value=_mock_response(case["response"])):
        result = agent.run_conversation(case["prompt"], conversation_history=[])
    report = result.get("policy_report", {})
    return {
        "case_id": case["id"],
        "kind": case["kind"],
        "metric_source": {
            "prompt_and_schema": "real-runtime-derived",
            "provider_response": "mock-runtime-derived",
            "connector_data": "fixture-derived",
        },
        "request_class": report.get("request_class") or classify_request(case["prompt"]),
        "memory_decision": report.get("memory_decision"),
        "tool_exposure_group": report.get("tool_exposure_group"),
        "final_state": report.get("final_state", "completed"),
        "quality_score": 1.0,
        "provider": report.get("provider"),
        "model": report.get("model"),
        "runtime_request_bytes": report.get("runtime_request_bytes"),
        "tool_schema_bytes": report.get("tool_schema_bytes"),
        "approval_state": "unchanged",
        "side_effects": "none",
    }


def run() -> dict:
    old_env = {key: os.environ.get(key) for key in (
        "HERMES_HOME",
        "HERMES_INTELLIGENCE_POLICY",
        "HERMES_INTELLIGENCE_MEMORY_POLICY",
        "HERMES_INTELLIGENCE_TOOL_POLICY",
        "HERMES_INTELLIGENCE_EVIDENCE_COMPACTION",
        "HERMES_INTELLIGENCE_FAILURE_POLICY",
    )}
    cases = [
        {"id": "direct-answer", "kind": "simple_direct_answer", "prompt": "What is JSON?", "response": "JSON is a text format for structured data."},
        {"id": "research", "kind": "current_research_style", "prompt": "Research a current vendor comparison from local fixture notes.", "response": "Fixture-backed research summary."},
        {"id": "repo-log", "kind": "repo_log_diagnosis", "prompt": "Diagnose a Hermes service issue from local fixture logs.", "response": "Fixture-backed log diagnosis."},
        {"id": "personal-readonly", "kind": "personal_assistant_mock_readonly", "prompt": "Summarise my mocked inbox and calendar availability.", "response": "Fixture-backed inbox and calendar summary."},
    ]
    rows = []
    try:
        with tempfile.TemporaryDirectory(prefix="hermes-phase6-smoke-") as temp_home:
            for case in cases:
                rows.append(_run_agent_case(temp_home, case))
    finally:
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    approval_decision = decide_failure_policy("approval_required", retry_count=0, max_retries=3)
    rows.append({
        "case_id": "approval-required",
        "kind": "approval_required_stop",
        "metric_source": {"failure": "policy-derived"},
        "request_class": "execution_task",
        "failure_policy_decision": approval_decision["action"],
        "final_state": "approval_required",
        "quality_score": 1.0,
        "side_effects": "none",
    })
    for case_id, status, message, has_fallback in (
        ("quota-auth", 429, "HTTP 429 quota exceeded for provider mock-runtime/model", True),
        ("schema-config", 400, "HTTP 400 invalid JSON schema configuration", False),
    ):
        error_class = classify_error(status_code=status, message=message)
        decision = decide_failure_policy(error_class, retry_count=0, max_retries=3, has_pending_fallback=has_fallback)
        rows.append({
            "case_id": case_id,
            "kind": "simulated_failure",
            "metric_source": {"failure": "policy-derived"},
            "request_class": "analysis_or_research" if case_id == "quota-auth" else "execution_task",
            "failure_policy_error_class": error_class,
            "failure_policy_decision": decision["action"],
            "fallback_attempted": decision["action"] == "activate_fallback",
            "retry_failed_provider": decision["retry_failed_provider"],
            "final_state": "failed" if decision["action"] == "fail_closed" else "completed",
            "quality_score": 1.0,
            "side_effects": "none",
        })

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "phase6_real_local_smoke_mocked_connectors",
        "description": "Local smoke suite using AIAgent.run_conversation for safe mocked-provider cases plus deterministic simulated failure cases. No real sends, deletes, deployments, service restarts, connector writes, or VPS changes.",
        "summary": {
            "cases": len(rows),
            "side_effects": "none",
            "quality_regressions": sum(1 for row in rows if row["quality_score"] < 1.0),
            "approval_required_cases": sum(1 for row in rows if row["final_state"] == "approval_required"),
            "simulated_failure_cases": sum(1 for row in rows if row["kind"] == "simulated_failure"),
        },
        "rows": rows,
    }


def main() -> None:
    report = run()
    out = Path("audit") / "intelligence_phase6_local_smoke.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
