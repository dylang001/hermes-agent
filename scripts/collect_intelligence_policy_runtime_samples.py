#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


SAMPLES = [
    {
        "id": "research-runtime",
        "domain": "research",
        "prompt": "Research a current competitor and summarise its positioning from local fixture notes.",
        "response": "Fixture-backed research summary.",
    },
    {
        "id": "engineering-runtime",
        "domain": "engineering_ops",
        "prompt": "Diagnose a Hermes service issue from the provided local fixture log excerpt.",
        "response": "Fixture-backed engineering diagnosis.",
    },
    {
        "id": "personal-runtime",
        "domain": "personal_business",
        "prompt": "Find and summarise important unread emails from the mocked inbox fixture.",
        "response": "Fixture-backed inbox summary.",
    },
]


class _FixtureMemoryManager:
    providers = [object()]

    def initialize_all(self, **_kwargs):
        return None

    def build_system_prompt(self) -> str:
        return "Sanitized fixture memory policy note."

    def on_turn_start(self, *_args, **_kwargs):
        return None

    def prefetch_all(self, query: str, *, session_id: str = "") -> str:
        return f"Sanitized fixture recall for {session_id or 'session'}: {query[:48]}"

    def sync_all(self, *_args, **_kwargs):
        return None

    def queue_prefetch_all(self, *_args, **_kwargs):
        return None


def _mock_response(content: str):
    message = SimpleNamespace(content=content, tool_calls=None, reasoning=None, reasoning_content=None)
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(choices=[choice], model="mock-runtime/model", usage=None)


def _make_agent(temp_home: str, *, memory_policy_enabled: bool, tool_policy_enabled: bool):
    os.environ["HERMES_HOME"] = temp_home
    os.environ["HERMES_INTELLIGENCE_POLICY"] = "1"
    if memory_policy_enabled:
        os.environ["HERMES_INTELLIGENCE_MEMORY_POLICY"] = "1"
    else:
        os.environ.pop("HERMES_INTELLIGENCE_MEMORY_POLICY", None)
    if tool_policy_enabled:
        os.environ["HERMES_INTELLIGENCE_TOOL_POLICY"] = "1"
    else:
        os.environ.pop("HERMES_INTELLIGENCE_TOOL_POLICY", None)
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


def collect_samples() -> dict:
    old_home = os.environ.get("HERMES_HOME")
    old_flag = os.environ.get("HERMES_INTELLIGENCE_POLICY")
    old_memory_flag = os.environ.get("HERMES_INTELLIGENCE_MEMORY_POLICY")
    old_tool_flag = os.environ.get("HERMES_INTELLIGENCE_TOOL_POLICY")
    reports = []
    try:
        with tempfile.TemporaryDirectory(prefix="hermes-policy-runtime-") as temp_home:
            for mode, memory_enabled, tool_enabled in (
                ("phase1_5_observational_only", False, False),
                ("memory_policy_enabled", True, False),
                ("tool_policy_enabled", True, True),
            ):
                for sample in SAMPLES:
                    agent = _make_agent(temp_home, memory_policy_enabled=memory_enabled, tool_policy_enabled=tool_enabled)
                    with patch.object(agent, "_interruptible_api_call", return_value=_mock_response(sample["response"])):
                        result = agent.run_conversation(sample["prompt"], conversation_history=[])
                    report = result["policy_report"]
                    report["sample_id"] = sample["id"]
                    report["sample_domain"] = sample["domain"]
                    report["sample_mode"] = mode
                    report["sample_metric_source"] = {
                        "prompt_and_schema": "real-runtime-derived",
                        "tool_calls": "mock-runtime-derived",
                        "provider_response": "mock-runtime-derived",
                        "fixture_inputs": "fixture-derived",
                    }
                    reports.append(report)
    finally:
        if old_home is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = old_home
        if old_flag is None:
            os.environ.pop("HERMES_INTELLIGENCE_POLICY", None)
        else:
            os.environ["HERMES_INTELLIGENCE_POLICY"] = old_flag
        if old_memory_flag is None:
            os.environ.pop("HERMES_INTELLIGENCE_MEMORY_POLICY", None)
        else:
            os.environ["HERMES_INTELLIGENCE_MEMORY_POLICY"] = old_memory_flag
        if old_tool_flag is None:
            os.environ.pop("HERMES_INTELLIGENCE_TOOL_POLICY", None)
        else:
            os.environ["HERMES_INTELLIGENCE_TOOL_POLICY"] = old_tool_flag

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "phase3_mocked_real_runtime_tool_samples",
        "description": "Runs local AIAgent.run_conversation with mocked provider responses and sanitized fixture memory in observer-only, memory-policy, and tool-policy modes. No network, connector, service, or production config changes.",
        "reports": reports,
    }


def main() -> None:
    report = collect_samples()
    out = Path("audit") / "intelligence_policy_phase1_5_runtime_samples.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
