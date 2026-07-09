from __future__ import annotations

import json
from typing import Any

from agent.intelligence_policy import read_latest_report, report_path


def render_report(report: dict[str, Any]) -> str:
    lines = [
        "Intelligence policy run report",
        f"  request_class       : {report.get('request_class', 'unknown')}",
        f"  final_state         : {report.get('final_state', 'unknown')}",
        f"  provider/model      : {report.get('provider', '')}/{report.get('model', '')}",
        f"  system prompt       : {report.get('system_prompt_bytes', 0)} byte(s), ~{report.get('estimated_prompt_tokens', 0)} token(s)",
        f"  tool schema         : {report.get('tool_schema_bytes', 0)} byte(s), ~{report.get('tool_schema_estimated_tokens', 0)} token(s)",
        f"  volatile context    : {report.get('volatile_context_bytes', 0)} byte(s), ~{report.get('volatile_context_estimated_tokens', 0)} token(s)",
        f"  runtime request     : {report.get('runtime_request_bytes', 0)} byte(s), ~{report.get('runtime_request_estimated_tokens', 0)} token(s)",
        f"  memory              : {report.get('injected_memory_count', 0)} block(s), ~{report.get('injected_memory_estimated_tokens', 0)} token(s)",
        f"  memory sources      : {report.get('injected_memory_sources', {})}",
        f"  memory policy       : enabled={report.get('memory_policy_enabled', False)} decision={report.get('memory_decision', 'disabled')} reason={report.get('memory_reason_code', '')}",
        f"  memory before/after : {report.get('memory_entries_considered', 0)}->{report.get('memory_entries_injected', 0)} entries, ~{report.get('memory_estimated_tokens_before', 0)}->{report.get('memory_estimated_tokens_after', 0)} token(s), saved ~{report.get('memory_estimated_savings', 0)}",
        f"  tool policy         : enabled={report.get('tool_policy_enabled', False)} group={report.get('tool_exposure_group', 'disabled')} fallback={report.get('tool_policy_fallback_reason', '')}",
        f"  tool schema policy  : {report.get('tools_available_before_policy', 0)}->{report.get('tools_exposed_after_policy', 0)} tools, {report.get('tool_schema_bytes_before_policy', 0)}->{report.get('tool_schema_bytes_after_policy', 0)} bytes, saved ~{report.get('tool_schema_estimated_token_savings', 0)} token(s)",
        f"  omitted categories  : {report.get('omitted_tool_categories', [])}",
        f"  write tools excluded: {report.get('write_capable_tools_excluded', False)}",
        f"  mcp startup during prep: {report.get('mcp_started_during_request_preparation', False)}",
        f"  evidence compaction : enabled={report.get('evidence_compaction_enabled', False)} compacted={report.get('tool_results_compacted_count', 0)} spilled={report.get('raw_outputs_spilled_count', 0)} failures={report.get('compaction_failures_count', 0)} fallback_raw={report.get('fallback_to_raw_count', 0)}",
        f"  evidence bytes      : {report.get('total_original_tool_output_bytes', 0)}->{report.get('total_compacted_tool_output_bytes', 0)} saved={report.get('total_evidence_savings_bytes', 0)} byte(s), ~{report.get('total_evidence_savings_tokens', 0)} token(s)",
        f"  evidence types      : {report.get('result_types_compacted', {})}",
        f"  evidence redactions : {report.get('redaction_count', 0)} sensitive_detected={report.get('sensitive_content_detected_redacted', False)}",
        f"  tools               : {len(report.get('tools_exposed') or [])} exposed, {report.get('tool_attempts', 0)} called",
        f"  tool outcomes       : {report.get('tool_successes', 0)} succeeded, {report.get('tool_failures', 0)} failed",
        f"  retries             : {report.get('retry_count', 0)} {report.get('retry_reasons', {})}",
        f"  compaction_savings  : {report.get('compaction_savings_tokens', 0)} token(s)",
        f"  elapsed_ms          : {report.get('elapsed_ms', 0)}",
        f"  input/output tokens : {report.get('input_tokens', 0)}/{report.get('output_tokens', 0)}",
        f"  labels              : {report.get('measurement_labels', {})}",
        f"  tool budget         : {report.get('tool_budget_expectation', {})}",
        f"  feature flags       : {report.get('feature_flags_active', {})}",
    ]
    return "\n".join(lines)


def cmd_intelligence_policy(args: Any) -> None:
    report = read_latest_report()
    if report is None:
        print(f"No intelligence policy run report found at {report_path()}")
        return
    if getattr(args, "json", False):
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(render_report(report))
