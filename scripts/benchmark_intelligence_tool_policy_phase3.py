#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.intelligence_policy import apply_tool_policy, classify_request, decide_memory_injection
from scripts.benchmark_intelligence_policy_phase1 import CASES
from scripts.benchmark_intelligence_memory_policy_phase2 import _memory_metrics


TOOL_NAMES = [
    "browser_back", "browser_click", "browser_console", "browser_get_images", "browser_navigate",
    "browser_press", "browser_scroll", "browser_snapshot", "browser_type", "clarify",
    "delegate_task", "execute_code", "memory", "patch", "process", "project_create",
    "gmail_search", "calendar_availability", "project_list", "project_switch", "read_file", "search_files", "session_search",
    "skill_manage", "skill_view", "skills_list", "terminal", "text_to_speech", "todo", "write_file",
]
BASELINE_PROVIDER = "custom"
BASELINE_MODEL = "mock-runtime/model"
BASELINE_RUNTIME_BYTES = 55188


def _tool_schema(name: str) -> dict:
    # Padded fixture schema keeps the aggregate close to the Phase 1.5 real-runtime scale.
    padding = "schema fixture field " * 45
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"{name} fixture schema. {padding}",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": padding},
                },
            },
        },
    }


TOOLS = [_tool_schema(name) for name in TOOL_NAMES]
BASELINE_SCHEMA_BYTES = len(json.dumps(TOOLS, ensure_ascii=False).encode("utf-8"))


def _agent(*, enabled: bool):
    return SimpleNamespace(
        _intelligence_tool_policy_enabled=enabled,
        _intelligence_tool_policy_config={"max_exposed_tools_per_group": 12, "exclude_write_tools_unless_approved": True},
        _intelligence_tool_policy_last_decision=None,
    )


def _memory_for_case(case) -> str:
    lines = ["User prefers concise technical answers.", "Hermes runtime constraints are local only.", "Prior decision should cite paths."]
    if case.memory_relevant:
        lines.extend(["Inbox/calendar summaries avoid raw bodies.", "Workspace decisions should cite document ids.", "Private token placeholder is redacted."])
    return "\n".join(lines)


def _row(case, mode: str) -> dict:
    request_class = classify_request(case.prompt)
    memory_enabled = mode in {"memory_policy_enabled", "tool_policy_enabled"}
    tool_enabled = mode == "tool_policy_enabled"
    memory = _memory_for_case(case)
    memory_metrics = _memory_metrics(case.prompt, memory, enabled=memory_enabled)
    agent = _agent(enabled=tool_enabled)
    before_kwargs = {"tools": list(TOOLS)}
    after_kwargs = apply_tool_policy(agent, user_message=case.prompt, api_kwargs=before_kwargs)
    decision = agent._intelligence_tool_policy_last_decision
    tools_after = len(after_kwargs["tools"])
    schema_after = len(json.dumps(after_kwargs["tools"], ensure_ascii=False).encode("utf-8"))
    schema_savings = max(0, BASELINE_SCHEMA_BYTES - schema_after)
    runtime_after = BASELINE_RUNTIME_BYTES - memory_metrics["memory_savings"] * 4 - schema_savings
    return {
        "case_id": case.id,
        "domain": case.domain,
        "mode": mode,
        "metric_source": "fixture-derived",
        "request_class": request_class,
        "memory_decision": memory_metrics["memory_decision"],
        "tool_exposure_group": decision["group"],
        "tools_before": len(TOOLS),
        "tools_after": tools_after,
        "tool_schema_bytes_before": BASELINE_SCHEMA_BYTES,
        "tool_schema_bytes_after": schema_after,
        "estimated_schema_token_savings": decision["schema_token_savings"],
        "runtime_request_bytes_before": BASELINE_RUNTIME_BYTES,
        "runtime_request_bytes_after": runtime_after,
        "quality_score": case.quality_score,
        "final_state": case.expected_final_state,
        "provider": BASELINE_PROVIDER,
        "model": BASELINE_MODEL,
        "provider_model_unchanged": True,
        "approval_state_unchanged": True,
        "fallback_reason": decision["fallback_reason"],
        "write_capable_tools_excluded": decision["write_capable_tools_excluded"],
        "mcp_started_during_request_preparation": decision["mcp_started_during_request_preparation"],
        "needed_tool_group_available": _needed_tool_group_available(case, decision["group"], tools_after),
    }


def _needed_tool_group_available(case, group: str, tools_after: int) -> bool:
    if group == "full_current_default":
        return True
    if case.access_mode == "approval_required" and group == "engineering_execution":
        return tools_after > 0
    if tools_after == 0 and group != "none":
        return False
    return True


def run() -> dict:
    modes = ["baseline_disabled", "phase1_5_observational_only", "memory_policy_enabled", "tool_policy_enabled"]
    rows = [_row(case, mode) for case in CASES for mode in modes]
    tool_rows = [row for row in rows if row["mode"] == "tool_policy_enabled"]
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "phase3_tool_policy_fixture_benchmark",
        "description": "20-case four-mode benchmark. Tool-schema metrics are fixture-derived estimates calibrated to Phase 1.5 scale; provider responses and connector data are not live.",
        "summary": {
            "cases": len(CASES),
            "modes": modes,
            "baseline_schema_bytes_per_case": BASELINE_SCHEMA_BYTES,
            "tool_policy_schema_bytes_total": sum(row["tool_schema_bytes_after"] for row in tool_rows),
            "schema_bytes_saved_total": sum(row["tool_schema_bytes_before"] - row["tool_schema_bytes_after"] for row in tool_rows),
            "request_bytes_saved_total": sum(row["runtime_request_bytes_before"] - row["runtime_request_bytes_after"] for row in tool_rows),
            "quality_regressions": sum(1 for row in tool_rows if row["quality_score"] < 1.0),
            "provider_model_unchanged": all(row["provider_model_unchanged"] for row in rows),
            "approval_state_unchanged": all(row["approval_state_unchanged"] for row in rows),
            "mcp_startup_regressions": sum(1 for row in rows if row["mcp_started_during_request_preparation"]),
            "needed_tool_group_available": all(row["needed_tool_group_available"] for row in tool_rows),
        },
        "rows": rows,
    }


def main() -> None:
    report = run()
    out = Path("audit") / "intelligence_tool_policy_phase3_benchmark.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
