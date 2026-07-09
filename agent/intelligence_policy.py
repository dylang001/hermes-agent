from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

from hermes_constants import get_hermes_home

RequestClass = Literal["direct_answer", "scoped_lookup", "analysis_or_research", "execution_task", "deep_work"]
ErrorClass = Literal["transient", "auth_or_quota", "configuration_or_schema", "tool_unavailable", "approval_required"]
FinalState = Literal["completed", "blocked", "approval_required", "failed"]
MemoryDecision = Literal["disabled", "skipped", "light", "project", "user", "full"]
FailurePolicyAction = Literal["existing_retry", "activate_fallback", "fail_closed", "approval_required"]
ToolExposureGroup = Literal[
    "disabled",
    "none",
    "minimal_readonly",
    "research",
    "workspace_readonly",
    "personal_readonly",
    "engineering_readonly",
    "engineering_execution",
    "full_current_default",
]

_TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}
_FLAG_ENV = "HERMES_INTELLIGENCE_POLICY"
_MEMORY_FLAG_ENV = "HERMES_INTELLIGENCE_MEMORY_POLICY"
_TOOL_FLAG_ENV = "HERMES_INTELLIGENCE_TOOL_POLICY"
_EVIDENCE_FLAG_ENV = "HERMES_INTELLIGENCE_EVIDENCE_COMPACTION"
_FAILURE_FLAG_ENV = "HERMES_INTELLIGENCE_FAILURE_POLICY"
_REPORT_DIRNAME = "run_reports"
_DEFAULT_MEMORY_TOKEN_BUDGET = 400
_DEFAULT_MEMORY_MAX_ENTRIES = 4
_DEFAULT_TOOL_MAX_PER_GROUP = 12
_DEFAULT_EVIDENCE_MAX_BYTES = 4000
_DEFAULT_EVIDENCE_MAX_ERROR_LINES = 12
_DEFAULT_EVIDENCE_MAX_LOG_LINES = 40

TOOL_BUDGET_EXPECTATIONS: dict[RequestClass, dict[str, Any]] = {
    "direct_answer": {"range": "0-1", "metadata_only": True, "note": "No tool unless freshness or private data is required."},
    "scoped_lookup": {"range": "1-3", "metadata_only": True, "note": "Use a small number of relevant lookups."},
    "analysis_or_research": {"range": "2-8", "metadata_only": True, "note": "Gather enough evidence, then stop early when sufficient."},
    "execution_task": {"range": "task-dependent", "metadata_only": True, "note": "Focused verification required."},
    "deep_work": {"range": "plan-and-checkpoints", "metadata_only": True, "note": "Requires an explicit multi-step plan and checkpoints."},
}


def _rough_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def intelligence_policy_enabled(config: Optional[dict[str, Any]] = None) -> bool:
    raw_env = os.getenv(_FLAG_ENV)
    if raw_env is not None:
        return raw_env.strip().lower() in _TRUE_VALUES
    try:
        raw_cfg = ((config or {}).get("agent") or {}).get("intelligence_policy_enabled", False)
        if isinstance(raw_cfg, str):
            return raw_cfg.strip().lower() in _TRUE_VALUES
        return bool(raw_cfg)
    except Exception:
        return False


def intelligence_memory_policy_enabled(config: Optional[dict[str, Any]] = None) -> bool:
    raw_env = os.getenv(_MEMORY_FLAG_ENV)
    if raw_env is not None:
        return raw_env.strip().lower() in _TRUE_VALUES
    try:
        raw_cfg = ((config or {}).get("agent") or {}).get("intelligence_memory_policy_enabled", False)
        if isinstance(raw_cfg, str):
            return raw_cfg.strip().lower() in _TRUE_VALUES
        return bool(raw_cfg)
    except Exception:
        return False


def memory_policy_config(config: Optional[dict[str, Any]] = None) -> dict[str, int]:
    agent_cfg = (config or {}).get("agent") or {}
    return {
        "memory_token_budget": _positive_int(agent_cfg.get("intelligence_memory_token_budget"), _DEFAULT_MEMORY_TOKEN_BUDGET),
        "max_memory_entries": _positive_int(agent_cfg.get("intelligence_memory_max_entries"), _DEFAULT_MEMORY_MAX_ENTRIES),
    }


def intelligence_tool_policy_enabled(config: Optional[dict[str, Any]] = None) -> bool:
    raw_env = os.getenv(_TOOL_FLAG_ENV)
    if raw_env is not None:
        return raw_env.strip().lower() in _TRUE_VALUES
    try:
        raw_cfg = ((config or {}).get("agent") or {}).get("intelligence_tool_policy_enabled", False)
        if isinstance(raw_cfg, str):
            return raw_cfg.strip().lower() in _TRUE_VALUES
        return bool(raw_cfg)
    except Exception:
        return False


def tool_policy_config(config: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    agent_cfg = (config or {}).get("agent") or {}
    raw_include = agent_cfg.get("intelligence_tool_policy_always_include", [])
    raw_exclude_write = agent_cfg.get("intelligence_tool_policy_exclude_write_tools_unless_approved", True)
    raw_fallback = agent_cfg.get("intelligence_tool_policy_fallback_to_full_on_tool_miss", True)
    return {
        "max_exposed_tools_per_group": _positive_int(agent_cfg.get("intelligence_tool_policy_max_exposed_tools_per_group"), _DEFAULT_TOOL_MAX_PER_GROUP),
        "always_include_tools": _string_list(raw_include),
        "exclude_write_tools_unless_approved": _bool_config(raw_exclude_write, True),
        "fallback_to_full_on_tool_miss": _bool_config(raw_fallback, True),
    }


def intelligence_evidence_compaction_enabled(config: Optional[dict[str, Any]] = None) -> bool:
    raw_env = os.getenv(_EVIDENCE_FLAG_ENV)
    if raw_env is not None:
        return raw_env.strip().lower() in _TRUE_VALUES
    try:
        raw_cfg = ((config or {}).get("agent") or {}).get("intelligence_evidence_compaction_enabled", False)
        if isinstance(raw_cfg, str):
            return raw_cfg.strip().lower() in _TRUE_VALUES
        return bool(raw_cfg)
    except Exception:
        return False


def intelligence_failure_policy_enabled(config: Optional[dict[str, Any]] = None) -> bool:
    raw_env = os.getenv(_FAILURE_FLAG_ENV)
    if raw_env is not None:
        return raw_env.strip().lower() in _TRUE_VALUES
    try:
        raw_cfg = ((config or {}).get("agent") or {}).get("intelligence_failure_policy_enabled", False)
        if isinstance(raw_cfg, str):
            return raw_cfg.strip().lower() in _TRUE_VALUES
        return bool(raw_cfg)
    except Exception:
        return False


def evidence_compaction_config(config: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    agent_cfg = (config or {}).get("agent") or {}
    return {
        "max_compacted_evidence_bytes": _positive_int(agent_cfg.get("intelligence_evidence_max_compacted_bytes"), _DEFAULT_EVIDENCE_MAX_BYTES),
        "max_retained_error_lines": _positive_int(agent_cfg.get("intelligence_evidence_max_retained_error_lines"), _DEFAULT_EVIDENCE_MAX_ERROR_LINES),
        "max_retained_log_lines": _positive_int(agent_cfg.get("intelligence_evidence_max_retained_log_lines"), _DEFAULT_EVIDENCE_MAX_LOG_LINES),
        "raw_output_spill_dir": str(agent_cfg.get("intelligence_evidence_raw_output_spill_dir") or ""),
        "redact_secrets_before_spill": _bool_config(agent_cfg.get("intelligence_evidence_redact_secrets_before_spill", True), True),
        "enable_raw_output_references": _bool_config(agent_cfg.get("intelligence_evidence_enable_raw_output_references", False), False),
        "fallback_to_raw_on_compaction_failure": _bool_config(agent_cfg.get("intelligence_evidence_fallback_to_raw_on_compaction_failure", True), True),
    }


def tool_budget_expectation(request_class: RequestClass) -> dict[str, Any]:
    return dict(TOOL_BUDGET_EXPECTATIONS[request_class])


def classify_request(message: Any) -> RequestClass:
    text = _message_text(message).lower()
    if not text.strip():
        return "direct_answer"

    if re.search(r"\b(weather|forecast|temperature|rain|raining|snow|wind|humidity)\b", text):
        return "scoped_lookup"

    if any(marker in text for marker in ("deep research", "comprehensive", "full audit", "end to end", "before/after", "benchmark", "20 representative", "architecture audit")):
        return "deep_work"

    if re.search(r"\b(implement|fix|patch|edit|modify|create|delete|deploy|restart|commit)\b", text) or "run tests" in text or re.search(r"\bwrite\b", text):
        return "execution_task"

    bounded_single_source = any(marker in text for marker in ("one source", "single source", "only one source"))
    research_markers = (
        "analyze", "analyse", "audit", "investigate", "compare", "comparison", "research", "diagnose",
        "root cause", "why ", "article", "pdf", "citations", "cited evidence", "daily priorities", "briefing",
    )
    if any(marker in text for marker in research_markers) and not bounded_single_source:
        return "analysis_or_research"

    lookup_markers = (
        "look up", "lookup", "find ", "search", "latest", "today", "current", "status", "logs", "file",
        "where", "which", "availability", "calendar", "inbox", "unread",
    )
    if any(marker in text for marker in lookup_markers):
        return "scoped_lookup"

    return "direct_answer"


def classify_error(error: Any = None, *, status_code: Optional[int] = None, message: str = "") -> ErrorClass:
    text = " ".join(
        str(part)
        for part in (message, error, getattr(error, "message", None), getattr(error, "body", None), getattr(error, "response", None))
        if part is not None
    ).lower()
    code = status_code if status_code is not None else getattr(error, "status_code", None)

    if code in {401, 402, 403, 429}:
        return "auth_or_quota"
    if re.search(r"\b(unauthorized|forbidden|invalid api key|api key|quota|billing|credits?|rate limit|too many requests)\b", text):
        return "auth_or_quota"
    if re.search(r"\b(approval required|requires approval|denied by approval|pending approval|write approval)\b", text):
        return "approval_required"
    if re.search(r"\b(tool unavailable|unknown tool|tool not found|no such tool|mcp.*unavailable|server unavailable)\b", text):
        return "tool_unavailable"
    if code in {400, 404, 409, 422}:
        return "configuration_or_schema"
    if re.search(r"\b(schema|configuration|configured|invalid request|bad request|validation|json schema|unsupported parameter|missing required)\b", text):
        return "configuration_or_schema"
    return "transient"


def decide_failure_policy(
    error_class: ErrorClass,
    *,
    retry_count: int = 0,
    max_retries: int = 0,
    has_pending_fallback: bool = False,
) -> dict[str, Any]:
    """Return observationally safe Phase 5 recovery metadata.

    This is intentionally deterministic and content-free: raw provider
    payloads stay out of reports, and behavioral use is gated by
    intelligence_failure_policy_enabled at the call site.
    """
    if error_class == "auth_or_quota":
        action: FailurePolicyAction = "activate_fallback" if has_pending_fallback else "fail_closed"
        reason_code = "auth_or_quota_fallback" if has_pending_fallback else "auth_or_quota_no_fallback"
        return {
            "enabled": True,
            "error_class": error_class,
            "action": action,
            "retry_failed_provider": False,
            "fallback_allowed": has_pending_fallback,
            "fail_closed": not has_pending_fallback,
            "retry_count_at_decision": int(retry_count),
            "max_retries": int(max_retries),
            "reason_code": reason_code,
        }
    if error_class == "configuration_or_schema":
        return {
            "enabled": True,
            "error_class": error_class,
            "action": "fail_closed",
            "retry_failed_provider": False,
            "fallback_allowed": False,
            "fail_closed": True,
            "retry_count_at_decision": int(retry_count),
            "max_retries": int(max_retries),
            "reason_code": "configuration_or_schema_nonretryable",
        }
    if error_class == "approval_required":
        return {
            "enabled": True,
            "error_class": error_class,
            "action": "approval_required",
            "retry_failed_provider": False,
            "fallback_allowed": False,
            "fail_closed": True,
            "retry_count_at_decision": int(retry_count),
            "max_retries": int(max_retries),
            "reason_code": "approval_required_stop",
        }
    if error_class == "tool_unavailable":
        return {
            "enabled": True,
            "error_class": error_class,
            "action": "fail_closed",
            "retry_failed_provider": False,
            "fallback_allowed": False,
            "fail_closed": True,
            "retry_count_at_decision": int(retry_count),
            "max_retries": int(max_retries),
            "reason_code": "tool_unavailable_no_safe_fallback",
        }
    return {
        "enabled": True,
        "error_class": error_class,
        "action": "existing_retry",
        "retry_failed_provider": True,
        "fallback_allowed": False,
        "fail_closed": False,
        "retry_count_at_decision": int(retry_count),
        "max_retries": int(max_retries),
        "reason_code": "transient_existing_bounded_retry",
    }


def record_failure_policy_decision(agent: Any, decision: dict[str, Any]) -> None:
    sanitized = {
        "enabled": bool(decision.get("enabled", False)),
        "error_class": str(decision.get("error_class", "") or ""),
        "action": str(decision.get("action", "") or ""),
        "retry_failed_provider": bool(decision.get("retry_failed_provider", False)),
        "fallback_allowed": bool(decision.get("fallback_allowed", False)),
        "fallback_attempted": bool(decision.get("fallback_attempted", False)),
        "fallback_succeeded": bool(decision.get("fallback_succeeded", False)),
        "fail_closed": bool(decision.get("fail_closed", False)),
        "retry_count_at_decision": int(decision.get("retry_count_at_decision", 0) or 0),
        "max_retries": int(decision.get("max_retries", 0) or 0),
        "reason_code": str(decision.get("reason_code", "") or ""),
    }
    try:
        agent._intelligence_failure_policy_last_decision = sanitized
    except Exception:
        pass


@dataclass
class PolicyRunReport:
    enabled: bool
    observational_only: bool
    request_class: RequestClass
    provider: str
    model: str
    api_mode: str = ""
    system_prompt_bytes: int = 0
    estimated_prompt_tokens: int = 0
    tool_schema_bytes: int = 0
    tool_schema_estimated_tokens: int = 0
    volatile_context_bytes: int = 0
    volatile_context_estimated_tokens: int = 0
    runtime_request_bytes: int = 0
    runtime_request_estimated_tokens: int = 0
    request_message_count: int = 0
    injected_memory_count: int = 0
    injected_memory_estimated_tokens: int = 0
    injected_memory_sources: dict[str, dict[str, int]] = field(default_factory=dict)
    memory_policy_enabled: bool = False
    memory_decision: MemoryDecision = "disabled"
    memory_entries_considered: int = 0
    memory_entries_injected: int = 0
    memory_estimated_tokens_before: int = 0
    memory_estimated_tokens_after: int = 0
    memory_estimated_savings: int = 0
    memory_reason_code: str = "policy_disabled"
    memory_token_budget: int = 0
    memory_max_entries: int = 0
    tool_policy_enabled: bool = False
    tool_exposure_group: ToolExposureGroup = "disabled"
    tools_available_before_policy: int = 0
    tools_exposed_after_policy: int = 0
    tool_schema_bytes_before_policy: int = 0
    tool_schema_bytes_after_policy: int = 0
    tool_schema_estimated_token_savings: int = 0
    omitted_tool_categories: list[str] = field(default_factory=list)
    tool_policy_fallback_reason: str = ""
    write_capable_tools_excluded: bool = False
    mcp_started_during_request_preparation: bool = False
    evidence_compaction_enabled: bool = False
    tool_results_compacted_count: int = 0
    raw_outputs_spilled_count: int = 0
    total_original_tool_output_bytes: int = 0
    total_compacted_tool_output_bytes: int = 0
    total_evidence_savings_bytes: int = 0
    total_evidence_savings_tokens: int = 0
    compaction_failures_count: int = 0
    fallback_to_raw_count: int = 0
    redaction_count: int = 0
    result_types_compacted: dict[str, int] = field(default_factory=dict)
    largest_compaction_savings_by_tool: dict[str, int] = field(default_factory=dict)
    sensitive_content_detected_redacted: bool = False
    failure_policy_enabled: bool = False
    failure_policy_error_class: str = ""
    failure_policy_action: str = ""
    failure_policy_reason_code: str = ""
    failure_policy_retry_failed_provider: bool = False
    failure_policy_fallback_attempted: bool = False
    failure_policy_fallback_succeeded: bool = False
    failure_policy_fail_closed: bool = False
    feature_flags_active: dict[str, bool] = field(default_factory=dict)
    measurement_labels: dict[str, str] = field(default_factory=dict)
    tool_budget_expectation: dict[str, Any] = field(default_factory=dict)
    tools_exposed: list[str] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)
    tool_attempts: int = 0
    tool_successes: int = 0
    tool_failures: int = 0
    retry_count: int = 0
    retry_reasons: dict[str, int] = field(default_factory=dict)
    compaction_savings_tokens: int = 0
    elapsed_ms: int = 0
    final_state: FinalState = "failed"
    input_tokens: int = 0
    output_tokens: int = 0
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    session_id: str = ""
    task_id: str = ""
    turn_id: str = ""

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("started_at", None)
        data.pop("ended_at", None)
        return data


class PolicyRunObserver:
    def __init__(self, report: PolicyRunReport):
        self.report = report

    @classmethod
    def from_agent(
        cls,
        agent: Any,
        *,
        user_message: Any,
        system_prompt: str,
        task_id: str,
        turn_id: str,
        ext_prefetch_cache: str = "",
    ) -> "PolicyRunObserver":
        tools = getattr(agent, "tools", None) or []
        tool_names = _tool_names(tools)
        memory_count, memory_tokens, memory_sources = _estimate_injected_memory(agent, ext_prefetch_cache)
        memory_policy = getattr(agent, "_intelligence_memory_policy_last_decision", None) or {}
        tool_policy = getattr(agent, "_intelligence_tool_policy_last_decision", None) or {}
        evidence_stats = getattr(agent, "_intelligence_evidence_compaction_stats", None) or {}
        failure_policy = getattr(agent, "_intelligence_failure_policy_last_decision", None) or {}
        tools_json = json.dumps(tools, ensure_ascii=False, default=str)
        request_class = classify_request(user_message)
        report = PolicyRunReport(
            enabled=True,
            observational_only=True,
            request_class=request_class,
            provider=str(getattr(agent, "provider", "") or ""),
            model=str(getattr(agent, "model", "") or ""),
            api_mode=str(getattr(agent, "api_mode", "") or ""),
            system_prompt_bytes=len((system_prompt or "").encode("utf-8")),
            estimated_prompt_tokens=_rough_tokens(system_prompt or ""),
            tool_schema_bytes=len(tools_json.encode("utf-8")),
            tool_schema_estimated_tokens=_rough_tokens(tools_json),
            injected_memory_count=memory_count,
            injected_memory_estimated_tokens=memory_tokens,
            injected_memory_sources=memory_sources,
            memory_policy_enabled=bool(memory_policy.get("enabled", False)),
            memory_decision=str(memory_policy.get("decision", "disabled") or "disabled"),
            memory_entries_considered=int(memory_policy.get("entries_considered", memory_count) or 0),
            memory_entries_injected=int(memory_policy.get("entries_injected", memory_count) or 0),
            memory_estimated_tokens_before=int(memory_policy.get("estimated_tokens_before", memory_tokens) or 0),
            memory_estimated_tokens_after=int(memory_policy.get("estimated_tokens_after", memory_tokens) or 0),
            memory_estimated_savings=int(memory_policy.get("estimated_savings", 0) or 0),
            memory_reason_code=str(memory_policy.get("reason_code", "policy_disabled") or "policy_disabled"),
            memory_token_budget=int(memory_policy.get("token_budget", 0) or 0),
            memory_max_entries=int(memory_policy.get("max_entries", 0) or 0),
            tool_policy_enabled=bool(tool_policy.get("enabled", False)),
            tool_exposure_group=str(tool_policy.get("group", "disabled") or "disabled"),
            tools_available_before_policy=int(tool_policy.get("tools_before", len(tool_names)) or 0),
            tools_exposed_after_policy=int(tool_policy.get("tools_after", len(tool_names)) or 0),
            tool_schema_bytes_before_policy=int(tool_policy.get("schema_bytes_before", len(tools_json.encode("utf-8"))) or 0),
            tool_schema_bytes_after_policy=int(tool_policy.get("schema_bytes_after", len(tools_json.encode("utf-8"))) or 0),
            tool_schema_estimated_token_savings=int(tool_policy.get("schema_token_savings", 0) or 0),
            omitted_tool_categories=list(tool_policy.get("omitted_tool_categories", []) or []),
            tool_policy_fallback_reason=str(tool_policy.get("fallback_reason", "") or ""),
            write_capable_tools_excluded=bool(tool_policy.get("write_capable_tools_excluded", False)),
            mcp_started_during_request_preparation=bool(tool_policy.get("mcp_started_during_request_preparation", False)),
            evidence_compaction_enabled=bool(evidence_stats.get("enabled", False)),
            tool_results_compacted_count=int(evidence_stats.get("tool_results_compacted_count", 0) or 0),
            raw_outputs_spilled_count=int(evidence_stats.get("raw_outputs_spilled_count", 0) or 0),
            total_original_tool_output_bytes=int(evidence_stats.get("total_original_tool_output_bytes", 0) or 0),
            total_compacted_tool_output_bytes=int(evidence_stats.get("total_compacted_tool_output_bytes", 0) or 0),
            total_evidence_savings_bytes=int(evidence_stats.get("total_evidence_savings_bytes", 0) or 0),
            total_evidence_savings_tokens=int(evidence_stats.get("total_evidence_savings_tokens", 0) or 0),
            compaction_failures_count=int(evidence_stats.get("compaction_failures_count", 0) or 0),
            fallback_to_raw_count=int(evidence_stats.get("fallback_to_raw_count", 0) or 0),
            redaction_count=int(evidence_stats.get("redaction_count", 0) or 0),
            result_types_compacted=dict(evidence_stats.get("result_types_compacted", {}) or {}),
            largest_compaction_savings_by_tool=dict(evidence_stats.get("largest_compaction_savings_by_tool", {}) or {}),
            sensitive_content_detected_redacted=bool(evidence_stats.get("sensitive_content_detected_redacted", False)),
            failure_policy_enabled=bool(failure_policy.get("enabled", False)),
            failure_policy_error_class=str(failure_policy.get("error_class", "") or ""),
            failure_policy_action=str(failure_policy.get("action", "") or ""),
            failure_policy_reason_code=str(failure_policy.get("reason_code", "") or ""),
            failure_policy_retry_failed_provider=bool(failure_policy.get("retry_failed_provider", False)),
            failure_policy_fallback_attempted=bool(failure_policy.get("fallback_attempted", False)),
            failure_policy_fallback_succeeded=bool(failure_policy.get("fallback_succeeded", False)),
            failure_policy_fail_closed=bool(failure_policy.get("fail_closed", False)),
            feature_flags_active={
                "intelligence_policy": True,
                "intelligence_policy_observational_only": True,
                "intelligence_memory_policy": bool(memory_policy.get("enabled", False)),
                "intelligence_tool_policy": bool(tool_policy.get("enabled", False)),
                "intelligence_evidence_compaction": bool(evidence_stats.get("enabled", False)),
                "intelligence_failure_policy": bool(failure_policy.get("enabled", False)),
            },
            measurement_labels={
                "system_prompt_bytes": "observer_start_derived",
                "estimated_prompt_tokens": "observer_start_derived",
                "tool_schema_bytes": "observer_start_derived",
                "tool_schema_estimated_tokens": "observer_start_derived",
                "volatile_context_bytes": "not_captured",
                "volatile_context_estimated_tokens": "not_captured",
                "runtime_request_bytes": "not_captured",
                "runtime_request_estimated_tokens": "not_captured",
                "injected_memory_count": "observer_start_derived",
                "injected_memory_estimated_tokens": "observer_start_derived",
                "memory_policy": "policy_metadata_derived" if memory_policy else "policy_disabled",
                "tool_policy": "policy_metadata_derived" if tool_policy else "policy_disabled",
                "evidence_compaction": "runtime_tool_result_derived" if evidence_stats else "policy_disabled",
                "failure_policy": "runtime_error_derived" if failure_policy else "policy_disabled",
                "tools_exposed": "observer_start_derived",
                "tools_called": "real_runtime_derived",
                "retry_count": "real_runtime_derived",
                "elapsed_ms": "real_runtime_derived",
                "final_state": "real_runtime_derived",
            },
            tool_budget_expectation=tool_budget_expectation(request_class),
            tools_exposed=tool_names,
            session_id=str(getattr(agent, "session_id", "") or ""),
            task_id=task_id,
            turn_id=turn_id,
        )
        return cls(report)

    def record_runtime_request(self, *, api_kwargs: dict[str, Any], api_messages: Optional[list[dict[str, Any]]] = None) -> None:
        messages = _coerce_messages(api_kwargs.get("messages") or api_kwargs.get("input") or api_messages)
        tools = api_kwargs.get("tools") or []

        system_content = _first_system_content(messages)
        if system_content is not None:
            self.report.system_prompt_bytes = len(system_content.encode("utf-8"))
            self.report.estimated_prompt_tokens = _rough_tokens(system_content)

        tools_json = json.dumps(tools, ensure_ascii=False, default=str)
        volatile_messages = _volatile_messages(messages)
        volatile_json = json.dumps(volatile_messages, ensure_ascii=False, default=str)
        request_json = json.dumps({"messages": messages, "tools": tools}, ensure_ascii=False, default=str)

        self.report.tool_schema_bytes = len(tools_json.encode("utf-8"))
        self.report.tool_schema_estimated_tokens = _rough_tokens(tools_json)
        self.report.tool_schema_bytes_after_policy = len(tools_json.encode("utf-8"))
        if not self.report.tool_schema_bytes_before_policy:
            self.report.tool_schema_bytes_before_policy = self.report.tool_schema_bytes_after_policy
        self.report.tool_schema_estimated_token_savings = max(
            0,
            _rough_tokens("x" * self.report.tool_schema_bytes_before_policy) - self.report.tool_schema_estimated_tokens,
        )
        self.report.tools_exposed_after_policy = len(_tool_names(tools))
        self.report.volatile_context_bytes = len(volatile_json.encode("utf-8"))
        self.report.volatile_context_estimated_tokens = _rough_tokens(volatile_json)
        self.report.runtime_request_bytes = len(request_json.encode("utf-8"))
        self.report.runtime_request_estimated_tokens = _rough_tokens(request_json)
        self.report.request_message_count = len(messages)
        self.report.measurement_labels.update({
            "system_prompt_bytes": "real_runtime_derived",
            "estimated_prompt_tokens": "real_runtime_derived",
            "tool_schema_bytes": "real_runtime_derived",
            "tool_schema_estimated_tokens": "real_runtime_derived",
            "volatile_context_bytes": "real_runtime_derived",
            "volatile_context_estimated_tokens": "real_runtime_derived",
            "runtime_request_bytes": "real_runtime_derived",
            "runtime_request_estimated_tokens": "real_runtime_derived",
            "request_message_count": "real_runtime_derived",
            "tool_policy": "real_runtime_derived",
        })

    def record_tool(self, name: str, *, failed: bool = False) -> None:
        if name:
            self.report.tools_called.append(str(name))
        self.report.tool_attempts += 1
        if failed:
            self.report.tool_failures += 1
        else:
            self.report.tool_successes += 1

    def record_retry(self, reason: ErrorClass) -> None:
        self.report.retry_count += 1
        self.report.retry_reasons[reason] = self.report.retry_reasons.get(reason, 0) + 1

    def finish(self, agent: Any, *, completed: bool, failed: bool, interrupted: bool = False) -> dict[str, Any]:
        self.report.ended_at = time.time()
        self.report.elapsed_ms = int((self.report.ended_at - self.report.started_at) * 1000)
        self.report.input_tokens = int(getattr(agent, "session_input_tokens", 0) or 0)
        self.report.output_tokens = int(getattr(agent, "session_output_tokens", 0) or 0)
        self.report.compaction_savings_tokens = _estimate_compaction_savings(agent)
        _apply_evidence_stats_to_report(self.report, getattr(agent, "_intelligence_evidence_compaction_stats", None) or {})
        _apply_failure_policy_to_report(self.report, getattr(agent, "_intelligence_failure_policy_last_decision", None) or {})
        self.report.final_state = _final_state(completed=completed, failed=failed, interrupted=interrupted, retry_reasons=self.report.retry_reasons)
        data = self.report.public_dict()
        write_report(data)
        return data


def start_run_observer(agent: Any, *, user_message: Any, system_prompt: str, task_id: str, turn_id: str, ext_prefetch_cache: str = "") -> Optional[PolicyRunObserver]:
    if not getattr(agent, "_intelligence_policy_enabled", False):
        return None
    try:
        return PolicyRunObserver.from_agent(agent, user_message=user_message, system_prompt=system_prompt, task_id=task_id, turn_id=turn_id, ext_prefetch_cache=ext_prefetch_cache)
    except Exception:
        return None


def apply_memory_policy(
    agent: Any,
    *,
    user_message: Any,
    prefetched_memory: str,
) -> str:
    enabled = bool(getattr(agent, "_intelligence_memory_policy_enabled", False))
    request_class = classify_request(user_message)
    cfg = getattr(agent, "_intelligence_memory_policy_config", {}) or {}
    token_budget = _positive_int(cfg.get("memory_token_budget"), _DEFAULT_MEMORY_TOKEN_BUDGET)
    max_entries = _positive_int(cfg.get("max_memory_entries"), _DEFAULT_MEMORY_MAX_ENTRIES)
    before_entries = _memory_entry_count(prefetched_memory)
    before_tokens = _rough_tokens(prefetched_memory)

    if not enabled:
        _store_memory_policy_decision(
            agent,
            enabled=False,
            request_class=request_class,
            decision="disabled",
            reason_code="policy_disabled",
            before_entries=before_entries,
            after_entries=before_entries,
            before_tokens=before_tokens,
            after_tokens=before_tokens,
            token_budget=0,
            max_entries=0,
        )
        return prefetched_memory

    decision, reason_code = decide_memory_injection(user_message, request_class=request_class)
    if decision == "skipped":
        filtered = ""
    else:
        filtered = _cap_memory_text(prefetched_memory, token_budget=token_budget, max_entries=max_entries)

    after_entries = _memory_entry_count(filtered)
    after_tokens = _rough_tokens(filtered)
    _store_memory_policy_decision(
        agent,
        enabled=True,
        request_class=request_class,
        decision=decision,
        reason_code=reason_code,
        before_entries=before_entries,
        after_entries=after_entries,
        before_tokens=before_tokens,
        after_tokens=after_tokens,
        token_budget=token_budget,
        max_entries=max_entries,
    )
    return filtered


def apply_tool_policy(
    agent: Any,
    *,
    user_message: Any,
    api_kwargs: dict[str, Any],
) -> dict[str, Any]:
    tools = api_kwargs.get("tools") or []
    if not isinstance(tools, list):
        return api_kwargs
    enabled = bool(getattr(agent, "_intelligence_tool_policy_enabled", False))
    cfg = getattr(agent, "_intelligence_tool_policy_config", {}) or {}
    max_tools = _positive_int(cfg.get("max_exposed_tools_per_group"), _DEFAULT_TOOL_MAX_PER_GROUP)
    always_include = set(_string_list(cfg.get("always_include_tools", [])))
    exclude_write = _bool_config(cfg.get("exclude_write_tools_unless_approved", True), True)
    request_class = classify_request(user_message)
    before_names = _tool_names(tools)
    before_json = json.dumps(tools, ensure_ascii=False, default=str)

    if not enabled:
        _store_tool_policy_decision(
            agent,
            enabled=False,
            group="disabled",
            tools_before=before_names,
            tools_after=before_names,
            schema_bytes_before=len(before_json.encode("utf-8")),
            schema_bytes_after=len(before_json.encode("utf-8")),
            omitted_categories=[],
            fallback_reason="policy_disabled",
            write_excluded=False,
            mcp_started=False,
        )
        return api_kwargs

    group, fallback_reason = decide_tool_exposure_group(user_message, request_class=request_class)
    selected = tools if group == "full_current_default" else _select_tools_for_group(
        tools,
        group=group,
        max_tools=max_tools,
        always_include=always_include,
        exclude_write=exclude_write,
        approved=_execution_approved(user_message),
    )
    if group != "full_current_default" and _required_group_missing(group, selected):
        group = "full_current_default"
        fallback_reason = "required_tool_group_missing"
        selected = tools

    after_names = _tool_names(selected)
    after_json = json.dumps(selected, ensure_ascii=False, default=str)
    omitted_categories = sorted({_tool_category(name) for name in before_names if name not in set(after_names)})
    write_excluded = any(_is_write_tool(name) for name in before_names if name not in set(after_names))
    _store_tool_policy_decision(
        agent,
        enabled=True,
        group=group,
        tools_before=before_names,
        tools_after=after_names,
        schema_bytes_before=len(before_json.encode("utf-8")),
        schema_bytes_after=len(after_json.encode("utf-8")),
        omitted_categories=omitted_categories,
        fallback_reason=fallback_reason,
        write_excluded=write_excluded,
        mcp_started=False,
    )
    api_kwargs = dict(api_kwargs)
    api_kwargs["tools"] = selected
    return api_kwargs


def compact_tool_result(agent: Any, *, tool_name: str, result: Any) -> Any:
    if not getattr(agent, "_intelligence_evidence_compaction_enabled", False):
        return result
    if not isinstance(result, str):
        return result
    cfg = getattr(agent, "_intelligence_evidence_compaction_config", {}) or {}
    try:
        return _compact_tool_result_text(agent, tool_name=tool_name, text=result, cfg=cfg)
    except Exception:
        _record_compaction_failure(agent)
        if _bool_config(cfg.get("fallback_to_raw_on_compaction_failure", True), True):
            _record_fallback_to_raw(agent)
            return result
        return result


def _compact_tool_result_text(agent: Any, *, tool_name: str, text: str, cfg: dict[str, Any]) -> str:
    original_bytes = len(text.encode("utf-8"))
    result_type = _classify_tool_result(tool_name, text)
    redacted, redaction_count = _redact_sensitive(text)
    max_bytes = _positive_int(cfg.get("max_compacted_evidence_bytes"), _DEFAULT_EVIDENCE_MAX_BYTES)
    raw_ref = _spill_raw_evidence(agent, tool_name=tool_name, text=redacted, cfg=cfg) if _should_spill(redacted, cfg) else None
    key_findings, preserved, omitted = _summarize_evidence(
        redacted,
        result_type=result_type,
        max_error_lines=_positive_int(cfg.get("max_retained_error_lines"), _DEFAULT_EVIDENCE_MAX_ERROR_LINES),
        max_log_lines=_positive_int(cfg.get("max_retained_log_lines"), _DEFAULT_EVIDENCE_MAX_LOG_LINES),
    )
    compacted = _format_compact_evidence(
        tool_name=tool_name,
        result_type=result_type,
        raw_ref=raw_ref,
        original_bytes=original_bytes,
        compacted_bytes=0,
        savings_bytes=0,
        key_findings=key_findings,
        preserved=preserved,
        omitted=omitted,
    )
    compacted = _truncate_bytes(compacted, max_bytes)
    compacted_bytes = len(compacted.encode("utf-8"))
    savings = max(0, original_bytes - compacted_bytes)
    compacted = _format_compact_evidence(
        tool_name=tool_name,
        result_type=result_type,
        raw_ref=raw_ref,
        original_bytes=original_bytes,
        compacted_bytes=compacted_bytes,
        savings_bytes=savings,
        key_findings=key_findings,
        preserved=preserved,
        omitted=omitted,
    )
    compacted = _truncate_bytes(compacted, max_bytes)
    _record_evidence_compaction(
        agent,
        tool_name=tool_name,
        result_type=result_type,
        original_bytes=original_bytes,
        compacted_bytes=len(compacted.encode("utf-8")),
        redaction_count=redaction_count,
        spilled=raw_ref is not None,
    )
    return compacted


def decide_tool_exposure_group(message: Any, *, request_class: Optional[RequestClass] = None) -> tuple[ToolExposureGroup, str]:
    text = _message_text(message).lower()
    cls = request_class or classify_request(message)
    if _mentions_unknown_tool_or_connector(text):
        return "full_current_default", "unknown_tool_or_connector"
    if any(marker in text for marker in ("ambiguous", "whatever tool", "any tool", "all tools")):
        return "full_current_default", "ambiguous_request"
    if cls == "direct_answer":
        return "none", ""
    if _personal_tool_request(text):
        return "personal_readonly", ""
    if _research_tool_request(text):
        return "research", ""
    if _workspace_tool_request(text):
        return "workspace_readonly", ""
    if _engineering_request(text):
        if cls == "execution_task" and _execution_approved(message):
            return "engineering_execution", ""
        return "engineering_readonly", ""
    if cls == "scoped_lookup":
        return "minimal_readonly", ""
    if cls == "analysis_or_research":
        return "research", ""
    if cls == "execution_task":
        return "full_current_default", "execution_approval_ambiguous"
    if cls == "deep_work":
        return "full_current_default", "deep_work_uncapped_tool_need"
    return "full_current_default", "uncertain_classifier"


def decide_memory_injection(message: Any, *, request_class: Optional[RequestClass] = None) -> tuple[MemoryDecision, str]:
    text = _message_text(message).lower()
    cls = request_class or classify_request(message)
    explicit_prior = bool(re.search(r"\b(prior|previous|remember|last time|earlier|decision|decided|document|doc|history|context)\b", text))
    personal = bool(re.search(r"\b(my|me|i|inbox|email|emails|calendar|calendars|meeting|meetings|task|tasks|drive|clickup|obsidian|workspace)\b", text))
    project = bool(re.search(r"\b(hermes|repo|repository|runtime|service|logs?|config|file|branch|project|workspace)\b", text))
    external_current = bool(re.search(r"\b(current|latest|today|vendor|competitor|pricing|market|policy|regulation|product)\b", text))
    preference = bool(re.search(r"\b(preference|preferences|criteria|constraints|budget|recommend|recommendation|purchase)\b", text))
    sensitive = bool(re.search(r"\b(secret|password|token|api key|credential|private key|ssn|credit card)\b", text))

    if sensitive:
        return "skipped", "sensitive_or_private_memory_risk"
    if preference and (personal or "my " in text):
        return "user", "user_constraints_relevant"
    if cls == "direct_answer":
        if explicit_prior or personal or project:
            return "light", "explicit_context_reference"
        return "skipped", "generic_direct_answer"
    if cls == "scoped_lookup":
        if project or explicit_prior:
            return "project", "project_or_prior_lookup"
        if personal:
            return "user", "personal_lookup"
        return "skipped", "non_personal_lookup"
    if cls == "analysis_or_research":
        if project or explicit_prior:
            return "project", "project_research_constraints"
        if personal or preference:
            return "user", "user_constraints_relevant"
        if external_current:
            return "skipped", "external_current_research"
        return "light", "analysis_may_benefit_from_light_context"
    if cls == "execution_task":
        if project or explicit_prior:
            return "project", "execution_needs_project_context"
        if personal:
            return "user", "execution_needs_personal_context"
        return "skipped", "execution_without_context_reference"
    if cls == "deep_work":
        return "full", "deep_work_capped_relevant_context"
    return "skipped", "default_skip"


def record_runtime_request(agent: Any, *, api_kwargs: dict[str, Any], api_messages: Optional[list[dict[str, Any]]] = None) -> None:
    observer = getattr(agent, "_policy_run_observer", None)
    if observer is None:
        return
    try:
        _apply_tool_policy_metadata_to_report(observer.report, getattr(agent, "_intelligence_tool_policy_last_decision", None) or {})
        observer.record_runtime_request(api_kwargs=api_kwargs, api_messages=api_messages)
    except Exception:
        pass


def record_tool(agent: Any, name: str, *, failed: bool = False) -> None:
    observer = getattr(agent, "_policy_run_observer", None)
    if observer is None:
        return
    try:
        observer.record_tool(name, failed=failed)
    except Exception:
        pass


def record_retry(agent: Any, reason: ErrorClass) -> None:
    observer = getattr(agent, "_policy_run_observer", None)
    if observer is None:
        return
    try:
        observer.record_retry(reason)
    except Exception:
        pass


def finalize_run(agent: Any, *, completed: bool, failed: bool, interrupted: bool = False) -> Optional[dict[str, Any]]:
    observer = getattr(agent, "_policy_run_observer", None)
    if observer is None:
        return None
    try:
        return observer.finish(agent, completed=completed, failed=failed, interrupted=interrupted)
    except Exception:
        return None
    finally:
        try:
            agent._policy_run_observer = None
        except Exception:
            pass


def report_dir() -> Path:
    return get_hermes_home() / _REPORT_DIRNAME


def report_path() -> Path:
    return report_dir() / "latest_policy_run.json"


def write_report(data: dict[str, Any]) -> Path:
    path = report_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return path


def read_latest_report() -> Optional[dict[str, Any]]:
    path = report_path()
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _message_text(message: Any) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        parts = []
        for item in message:
            if isinstance(item, dict):
                value = item.get("text") or item.get("content") or ""
                if isinstance(value, str):
                    parts.append(value)
        return " ".join(parts)
    return str(message or "")


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except Exception:
        return default


def _memory_entry_count(text: str) -> int:
    if not text:
        return 0
    entries = [line for line in text.splitlines() if line.strip()]
    return max(1, len(entries))


def _cap_memory_text(text: str, *, token_budget: int, max_entries: int) -> str:
    if not text:
        return ""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        lines = [text.strip()]
    kept: list[str] = []
    used_tokens = 0
    for line in lines[:max_entries]:
        line_tokens = _rough_tokens(line)
        if kept and used_tokens + line_tokens > token_budget:
            break
        if not kept and line_tokens > token_budget:
            max_chars = max(0, token_budget * 4)
            kept.append(line[:max_chars])
            used_tokens = token_budget
            break
        kept.append(line)
        used_tokens += line_tokens
    return "\n".join(kept)


def _store_memory_policy_decision(
    agent: Any,
    *,
    enabled: bool,
    request_class: RequestClass,
    decision: MemoryDecision,
    reason_code: str,
    before_entries: int,
    after_entries: int,
    before_tokens: int,
    after_tokens: int,
    token_budget: int,
    max_entries: int,
) -> None:
    try:
        agent._intelligence_memory_policy_last_decision = {
            "enabled": enabled,
            "request_class": request_class,
            "decision": decision,
            "reason_code": reason_code,
            "entries_considered": before_entries,
            "entries_injected": after_entries,
            "estimated_tokens_before": before_tokens,
            "estimated_tokens_after": after_tokens,
            "estimated_savings": max(0, before_tokens - after_tokens),
            "token_budget": token_budget,
            "max_entries": max_entries,
        }
    except Exception:
        pass


def _store_tool_policy_decision(
    agent: Any,
    *,
    enabled: bool,
    group: ToolExposureGroup,
    tools_before: list[str],
    tools_after: list[str],
    schema_bytes_before: int,
    schema_bytes_after: int,
    omitted_categories: list[str],
    fallback_reason: str,
    write_excluded: bool,
    mcp_started: bool,
) -> None:
    try:
        agent._intelligence_tool_policy_last_decision = {
            "enabled": enabled,
            "group": group,
            "tools_before": len(tools_before),
            "tools_after": len(tools_after),
            "tool_names_before": sorted(tools_before),
            "tool_names_after": sorted(tools_after),
            "schema_bytes_before": schema_bytes_before,
            "schema_bytes_after": schema_bytes_after,
            "schema_token_savings": max(0, _rough_tokens("x" * schema_bytes_before) - _rough_tokens("x" * schema_bytes_after)),
            "omitted_tool_categories": omitted_categories,
            "fallback_reason": fallback_reason,
            "write_capable_tools_excluded": write_excluded,
            "mcp_started_during_request_preparation": mcp_started,
        }
    except Exception:
        pass


def _apply_tool_policy_metadata_to_report(report: PolicyRunReport, tool_policy: dict[str, Any]) -> None:
    if not tool_policy:
        return
    report.tool_policy_enabled = bool(tool_policy.get("enabled", False))
    report.tool_exposure_group = str(tool_policy.get("group", "disabled") or "disabled")
    report.tools_available_before_policy = int(tool_policy.get("tools_before", 0) or 0)
    report.tools_exposed_after_policy = int(tool_policy.get("tools_after", 0) or 0)
    report.tool_schema_bytes_before_policy = int(tool_policy.get("schema_bytes_before", 0) or 0)
    report.tool_schema_bytes_after_policy = int(tool_policy.get("schema_bytes_after", 0) or 0)
    report.tool_schema_estimated_token_savings = int(tool_policy.get("schema_token_savings", 0) or 0)
    report.omitted_tool_categories = list(tool_policy.get("omitted_tool_categories", []) or [])
    report.tool_policy_fallback_reason = str(tool_policy.get("fallback_reason", "") or "")
    report.write_capable_tools_excluded = bool(tool_policy.get("write_capable_tools_excluded", False))
    report.mcp_started_during_request_preparation = bool(tool_policy.get("mcp_started_during_request_preparation", False))
    report.feature_flags_active["intelligence_tool_policy"] = bool(tool_policy.get("enabled", False))
    report.measurement_labels["tool_policy"] = "real_runtime_derived"


def _apply_evidence_stats_to_report(report: PolicyRunReport, stats: dict[str, Any]) -> None:
    if not stats:
        return
    report.evidence_compaction_enabled = bool(stats.get("enabled", False))
    report.tool_results_compacted_count = int(stats.get("tool_results_compacted_count", 0) or 0)
    report.raw_outputs_spilled_count = int(stats.get("raw_outputs_spilled_count", 0) or 0)
    report.total_original_tool_output_bytes = int(stats.get("total_original_tool_output_bytes", 0) or 0)
    report.total_compacted_tool_output_bytes = int(stats.get("total_compacted_tool_output_bytes", 0) or 0)
    report.total_evidence_savings_bytes = int(stats.get("total_evidence_savings_bytes", 0) or 0)
    report.total_evidence_savings_tokens = int(stats.get("total_evidence_savings_tokens", 0) or 0)
    report.compaction_failures_count = int(stats.get("compaction_failures_count", 0) or 0)
    report.fallback_to_raw_count = int(stats.get("fallback_to_raw_count", 0) or 0)
    report.redaction_count = int(stats.get("redaction_count", 0) or 0)
    report.result_types_compacted = dict(stats.get("result_types_compacted", {}) or {})
    report.largest_compaction_savings_by_tool = dict(stats.get("largest_compaction_savings_by_tool", {}) or {})
    report.sensitive_content_detected_redacted = bool(stats.get("sensitive_content_detected_redacted", False))
    report.feature_flags_active["intelligence_evidence_compaction"] = bool(stats.get("enabled", False))
    report.measurement_labels["evidence_compaction"] = "runtime_tool_result_derived"


def _classify_tool_result(tool_name: str, text: str) -> str:
    lower_tool = tool_name.lower()
    lower = text[:2000].lower()
    if "traceback" in lower:
        return "error"
    if lower_tool in {"terminal", "process", "execute_code"} or re.search(r"\b(info|warn|error|debug)\b.*\\d{2}:\\d{2}:\\d{2}", lower):
        return "logs"
    if re.search(r"\berror\b|\bexception\b", lower):
        return "error"
    if lower_tool.startswith("browser_") or "http://" in lower or "https://" in lower or "citation" in lower:
        return "web"
    if lower.strip().startswith(("{", "[")):
        return "json"
    if lower_tool in {"gmail_search", "calendar_availability", "task_lookup"} or "email" in lower or "calendar" in lower:
        return "connector"
    if lower_tool in {"read_file", "search_files"} or re.search(r"[/\\][\\w./-]+:\\d+", text):
        return "file"
    return "text"


def _summarize_evidence(text: str, *, result_type: str, max_error_lines: int, max_log_lines: int) -> tuple[list[str], list[str], list[str]]:
    lines = [line.rstrip() for line in text.splitlines()]
    nonempty = [line for line in lines if line.strip()]
    deduped = _dedupe_preserve_order(nonempty)
    key_findings: list[str] = []
    preserved: list[str] = []
    omitted: list[str] = []
    if result_type == "json":
        key_findings, preserved = _summarize_json(text)
    elif result_type == "error":
        preserved = [line for line in deduped if _important_evidence_line(line)][:max_error_lines]
        key_findings = preserved[:5]
    elif result_type == "logs":
        important = [line for line in deduped if _important_evidence_line(line)]
        preserved = (important or deduped)[:max_log_lines]
        key_findings = important[:8] or preserved[:5]
        omitted.append("repeated log lines and low-signal status chatter")
    elif result_type == "web":
        preserved = [line for line in deduped if _important_evidence_line(line) or re.search(r"\b(title|source|date|claim|citation|url)\b", line, re.I)][:20]
        key_findings = preserved[:8] or deduped[:5]
    elif result_type == "connector":
        preserved = [line for line in deduped if _important_evidence_line(line) or re.search(r"\b(id|subject|from|to|date|time|status|meeting|task)\b", line, re.I)][:20]
        key_findings = preserved[:8] or ["Connector payload summarized; raw private body omitted."]
        omitted.append("raw private connector body content")
    elif result_type == "file":
        preserved = [line for line in deduped if _important_evidence_line(line) or re.search(r"\b(file|path|line|def |class |import |error)\b", line, re.I)][:24]
        key_findings = preserved[:8] or deduped[:5]
    else:
        preserved = deduped[:20]
        key_findings = preserved[:8]
    if len(deduped) < len(nonempty):
        omitted.append(f"{len(nonempty) - len(deduped)} duplicate line(s)")
    if not key_findings:
        key_findings = ["No high-signal findings detected in compacted output."]
    if not preserved:
        preserved = key_findings[:]
    if not omitted:
        omitted = ["low-signal repeated or verbose content"]
    return key_findings, preserved, omitted


def _summarize_json(text: str) -> tuple[list[str], list[str]]:
    try:
        payload = json.loads(text)
    except Exception:
        return (["Invalid JSON-like payload; preserved important text lines."], [line for line in text.splitlines() if _important_evidence_line(line)][:20])
    findings: list[str] = []
    preserved: list[str] = []
    for path, value in _walk_json(payload):
        lower_path = path.lower()
        if any(key in lower_path for key in ("id", "status", "timestamp", "date", "error", "url", "source")):
            item = f"{path}: {value}"
            preserved.append(item)
            if any(key in lower_path for key in ("status", "error")):
                findings.append(item)
    return (findings[:8] or preserved[:8] or ["JSON payload compacted."], preserved[:30] or ["No key JSON fields found."])


def _walk_json(value: Any, prefix: str = "$"):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_json(child, f"{prefix}.{key}")
    elif isinstance(value, list):
        for idx, child in enumerate(value[:20]):
            yield from _walk_json(child, f"{prefix}[{idx}]")
    else:
        yield prefix, value


def _dedupe_preserve_order(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = line.strip()
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
    return out


def _important_evidence_line(line: str) -> bool:
    return bool(re.search(r"(error|exception|failed|status|http\s*\d{3}|provider|model|quota|auth|unauthorized|forbidden|timeout|timed out|schema|configuration|approval required|id[:= ]|timestamp|\d{4}-\d{2}-\d{2}|https?://|[/\\][\w./-]+:\d+|File\s+\".+\",\s+line\s+\d+|\bline \d+\b|traceback|source|citation)", line, re.I))


def _format_compact_evidence(
    *,
    tool_name: str,
    result_type: str,
    raw_ref: Optional[str],
    original_bytes: int,
    compacted_bytes: int,
    savings_bytes: int,
    key_findings: list[str],
    preserved: list[str],
    omitted: list[str],
) -> str:
    return "\n".join(
        [
            "[compact_tool_evidence]",
            f"tool: {tool_name}",
            f"type: {result_type}",
            f"raw_ref: {raw_ref or 'null'}",
            f"original_bytes: {original_bytes}",
            f"compacted_bytes: {compacted_bytes}",
            f"savings_bytes: {savings_bytes}",
            "key_findings:",
            *[f"- {item}" for item in key_findings[:12]],
            "preserved_evidence:",
            *[f"- {item}" for item in preserved[:30]],
            "omitted:",
            *[f"- {item}" for item in omitted[:12]],
            "[/compact_tool_evidence]",
        ]
    )


def _redact_sensitive(text: str) -> tuple[str, int]:
    patterns = [
        r"(?i)(api[_-]?key|token|password|secret|credential)\\s*[:=]\\s*['\"]?([A-Za-z0-9_./+=-]{8,})",
        r"sk-[A-Za-z0-9]{16,}",
        r"(?i)bearer\\s+[A-Za-z0-9_./+=-]{12,}",
    ]
    count = 0
    redacted = text
    for pattern in patterns:
        redacted, n = re.subn(pattern, lambda m: m.group(0).split(m.group(2))[0] + "[REDACTED]" if len(m.groups()) >= 2 else "[REDACTED]", redacted)
        count += n
    return redacted, count


def _should_spill(text: str, cfg: dict[str, Any]) -> bool:
    return _bool_config(cfg.get("enable_raw_output_references", False), False) and len(text.encode("utf-8")) > _positive_int(cfg.get("max_compacted_evidence_bytes"), _DEFAULT_EVIDENCE_MAX_BYTES)


def _spill_raw_evidence(agent: Any, *, tool_name: str, text: str, cfg: dict[str, Any]) -> Optional[str]:
    if not _bool_config(cfg.get("redact_secrets_before_spill", True), True):
        text, _ = _redact_sensitive(text)
    spill_root = str(cfg.get("raw_output_spill_dir") or "").strip()
    base = Path(spill_root) if spill_root else get_hermes_home() / "evidence_spills"
    try:
        base.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = base / f"{int(time.time() * 1000)}-{re.sub(r'[^A-Za-z0-9_.-]+', '_', tool_name)[:40]}.txt"
        path.write_text(text, encoding="utf-8")
        try:
            path.chmod(0o600)
        except Exception:
            pass
        return str(path)
    except Exception:
        return None


def _truncate_bytes(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore") + "\n- truncated to evidence budget"


def _ensure_evidence_stats(agent: Any) -> dict[str, Any]:
    stats = getattr(agent, "_intelligence_evidence_compaction_stats", None)
    if not isinstance(stats, dict):
        stats = {
            "enabled": bool(getattr(agent, "_intelligence_evidence_compaction_enabled", False)),
            "tool_results_compacted_count": 0,
            "raw_outputs_spilled_count": 0,
            "total_original_tool_output_bytes": 0,
            "total_compacted_tool_output_bytes": 0,
            "total_evidence_savings_bytes": 0,
            "total_evidence_savings_tokens": 0,
            "compaction_failures_count": 0,
            "fallback_to_raw_count": 0,
            "redaction_count": 0,
            "result_types_compacted": {},
            "largest_compaction_savings_by_tool": {},
            "sensitive_content_detected_redacted": False,
        }
        agent._intelligence_evidence_compaction_stats = stats
    return stats


def _record_evidence_compaction(agent: Any, *, tool_name: str, result_type: str, original_bytes: int, compacted_bytes: int, redaction_count: int, spilled: bool) -> None:
    stats = _ensure_evidence_stats(agent)
    savings = max(0, original_bytes - compacted_bytes)
    stats["enabled"] = True
    stats["tool_results_compacted_count"] += 1
    stats["raw_outputs_spilled_count"] += 1 if spilled else 0
    stats["total_original_tool_output_bytes"] += original_bytes
    stats["total_compacted_tool_output_bytes"] += compacted_bytes
    stats["total_evidence_savings_bytes"] += savings
    stats["total_evidence_savings_tokens"] += _rough_tokens("x" * savings)
    stats["redaction_count"] += redaction_count
    stats["sensitive_content_detected_redacted"] = stats["sensitive_content_detected_redacted"] or redaction_count > 0
    stats["result_types_compacted"][result_type] = stats["result_types_compacted"].get(result_type, 0) + 1
    prev = stats["largest_compaction_savings_by_tool"].get(tool_name, 0)
    stats["largest_compaction_savings_by_tool"][tool_name] = max(prev, savings)


def _record_compaction_failure(agent: Any) -> None:
    stats = _ensure_evidence_stats(agent)
    stats["enabled"] = True
    stats["compaction_failures_count"] += 1


def _record_fallback_to_raw(agent: Any) -> None:
    stats = _ensure_evidence_stats(agent)
    stats["enabled"] = True
    stats["fallback_to_raw_count"] += 1


def _select_tools_for_group(
    tools: list[dict[str, Any]],
    *,
    group: ToolExposureGroup,
    max_tools: int,
    always_include: set[str],
    exclude_write: bool,
    approved: bool,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    allowed = _allowed_categories(group)
    for tool in tools:
        name = _tool_name(tool)
        if not name:
            continue
        category = _tool_category(name)
        if name in always_include or category in allowed:
            if exclude_write and _is_write_tool(name) and not (group == "engineering_execution" and approved):
                continue
            selected.append(tool)
        if len(selected) >= max_tools:
            break
    return selected


def _allowed_categories(group: ToolExposureGroup) -> set[str]:
    if group == "none":
        return set()
    if group == "minimal_readonly":
        return {"workspace_readonly", "engineering_readonly", "utility_readonly"}
    if group == "research":
        return {"research", "browser_readonly"}
    if group == "workspace_readonly":
        return {"workspace_readonly", "engineering_readonly", "utility_readonly"}
    if group == "personal_readonly":
        return {"personal_readonly", "utility_readonly"}
    if group == "engineering_readonly":
        return {"engineering_readonly", "workspace_readonly", "utility_readonly"}
    if group == "engineering_execution":
        return {"engineering_readonly", "workspace_readonly", "engineering_execution", "utility_readonly"}
    return {"full"}


def _required_group_missing(group: ToolExposureGroup, selected: list[dict[str, Any]]) -> bool:
    if group in {"none", "full_current_default", "disabled"}:
        return False
    names = _tool_names(selected)
    if group == "research":
        return not any(_tool_category(name) in {"research", "browser_readonly"} for name in names)
    if group == "personal_readonly":
        return not any(_tool_category(name) == "personal_readonly" for name in names)
    if group == "engineering_execution":
        return not any(_tool_category(name) == "engineering_execution" for name in names)
    return not names


def _tool_name(tool: Any) -> str:
    if isinstance(tool, dict):
        return str(tool.get("function", {}).get("name") or "")
    return ""


def _tool_category(name: str) -> str:
    lower = name.lower()
    if lower in {"gmail_search", "gmail_read", "calendar_availability", "calendar_read", "contacts_search", "task_lookup"}:
        return "personal_readonly"
    if lower.startswith("browser_"):
        return "browser_readonly"
    if lower in {"web_search", "web_extract", "search_web", "fetch_url"}:
        return "research"
    if lower in {"read_file", "search_files", "session_search", "project_list", "skill_view", "skills_list", "memory"}:
        return "workspace_readonly"
    if lower in {"terminal", "execute_code", "process"}:
        return "engineering_execution"
    if lower in {"patch", "write_file", "project_create", "project_switch", "todo"}:
        return "engineering_execution"
    if lower in {"clarify", "delegate_task", "text_to_speech", "skill_manage"}:
        return "utility_readonly"
    return "unknown"


def _is_write_tool(name: str) -> bool:
    lower = name.lower()
    return lower in {"patch", "write_file", "project_create", "project_switch", "terminal", "execute_code", "process", "todo"}


def _execution_approved(message: Any) -> bool:
    text = _message_text(message).lower()
    return bool(re.search(r"\b(approved|approval granted|you may edit|go ahead|apply the patch)\b", text))


def _research_tool_request(text: str) -> bool:
    return bool(re.search(r"\b(web|current|latest|competitor|vendor|pricing|market|policy|regulation|article|pdf|sources?|weather|forecast|temperature|rain|raining|snow|wind|humidity)\b", text))


def _personal_tool_request(text: str) -> bool:
    return bool(re.search(r"\b(inbox|email|emails|gmail|calendar|meeting|contacts?|tasks?)\b", text))


def _workspace_tool_request(text: str) -> bool:
    return bool(re.search(r"\b(prior|decision|document|drive|clickup|obsidian|workspace|file|repo|repository)\b", text))


def _engineering_request(text: str) -> bool:
    return bool(re.search(r"\b(hermes|logs?|runtime|service|config|health|bug|code|patch|tests?|ci|deploy)\b", text))


def _mentions_unknown_tool_or_connector(text: str) -> bool:
    known = (
        "gmail", "calendar", "drive", "clickup", "obsidian", "file", "repo", "browser", "web",
        "hermes", "logs", "terminal", "patch", "email", "inbox",
    )
    if "tool" in text or "connector" in text or "mcp" in text:
        return not any(item in text for item in known)
    return False


def _bool_config(value: Any, default: bool) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in _TRUE_VALUES
    if value is None:
        return default
    return bool(value)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(part).strip() for part in value if str(part).strip()]
    return []


def _tool_names(tools: Any) -> list[str]:
    try:
        return sorted(str(t.get("function", {}).get("name")) for t in tools if isinstance(t, dict) and t.get("function", {}).get("name"))
    except Exception:
        return []


def _coerce_messages(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _first_system_content(messages: list[dict[str, Any]]) -> Optional[str]:
    for message in messages:
        if message.get("role") != "system":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False, default=str)
    return None


def _volatile_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if messages and messages[0].get("role") == "system":
        return messages[1:]
    return messages


def _estimate_injected_memory(agent: Any, ext_prefetch_cache: str) -> tuple[int, int, dict[str, dict[str, int]]]:
    sources: dict[str, dict[str, int]] = {}

    def add_source(category: str, block: str) -> None:
        if not block:
            return
        entry = sources.setdefault(category, {"count": 0, "estimated_tokens": 0})
        entry["count"] += 1
        entry["estimated_tokens"] += _rough_tokens(block)

    store = getattr(agent, "_memory_store", None)
    if store is not None:
        try:
            if getattr(agent, "_memory_enabled", True):
                add_source("project_memory", store.format_for_system_prompt("memory") or "")
            if getattr(agent, "_user_profile_enabled", True):
                add_source("user_profile", store.format_for_system_prompt("user") or "")
        except Exception:
            pass
    manager = getattr(agent, "_memory_manager", None)
    if manager is not None:
        try:
            add_source("external_memory_system_prompt", manager.build_system_prompt() or "")
        except Exception:
            pass
    if ext_prefetch_cache:
        add_source("external_memory_prefetch", ext_prefetch_cache)
    return (
        sum(entry["count"] for entry in sources.values()),
        sum(entry["estimated_tokens"] for entry in sources.values()),
        sources,
    )


def _estimate_compaction_savings(agent: Any) -> int:
    compressor = getattr(agent, "context_compressor", None)
    if compressor is None:
        return 0
    rough = int(getattr(compressor, "last_compression_rough_tokens", 0) or 0)
    prompt = int(getattr(compressor, "last_prompt_tokens", 0) or 0)
    if rough > 0 and prompt >= 0 and rough > prompt:
        return rough - prompt
    return 0


def _apply_failure_policy_to_report(report: PolicyRunReport, decision: dict[str, Any]) -> None:
    if not decision:
        report.feature_flags_active.setdefault("intelligence_failure_policy", False)
        report.measurement_labels.setdefault("failure_policy", "policy_disabled")
        return
    report.failure_policy_enabled = bool(decision.get("enabled", False))
    report.failure_policy_error_class = str(decision.get("error_class", "") or "")
    report.failure_policy_action = str(decision.get("action", "") or "")
    report.failure_policy_reason_code = str(decision.get("reason_code", "") or "")
    report.failure_policy_retry_failed_provider = bool(decision.get("retry_failed_provider", False))
    report.failure_policy_fallback_attempted = bool(decision.get("fallback_attempted", False))
    report.failure_policy_fallback_succeeded = bool(decision.get("fallback_succeeded", False))
    report.failure_policy_fail_closed = bool(decision.get("fail_closed", False))
    report.feature_flags_active["intelligence_failure_policy"] = bool(decision.get("enabled", False))
    report.measurement_labels["failure_policy"] = "runtime_error_derived"


def _final_state(*, completed: bool, failed: bool, interrupted: bool, retry_reasons: Optional[dict[str, int]] = None) -> FinalState:
    if retry_reasons and retry_reasons.get("approval_required", 0) > 0:
        return "approval_required"
    if completed and not failed and not interrupted:
        return "completed"
    if failed:
        return "failed"
    return "blocked"
