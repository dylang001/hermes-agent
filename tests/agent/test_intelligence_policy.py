from __future__ import annotations

from types import SimpleNamespace

from agent.intelligence_policy import (
    PolicyRunObserver,
    apply_memory_policy,
    apply_tool_policy,
    classify_error,
    classify_request,
    compact_tool_result,
    decide_failure_policy,
    decide_memory_injection,
    decide_tool_exposure_group,
    evidence_compaction_config,
    finalize_run,
    intelligence_evidence_compaction_enabled,
    intelligence_failure_policy_enabled,
    intelligence_memory_policy_enabled,
    intelligence_policy_enabled,
    intelligence_tool_policy_enabled,
    memory_policy_config,
    record_failure_policy_decision,
    record_runtime_request,
    record_tool,
    start_run_observer,
    tool_budget_expectation,
    tool_policy_config,
)


class _MemoryManager:
    def build_system_prompt(self):
        return "External memory fact"


def _agent(enabled=True):
    return SimpleNamespace(
        _intelligence_policy_enabled=enabled,
        _policy_run_observer=None,
        provider="custom",
        model="mock-runtime/model",
        api_mode="openai",
        session_id="s1",
        tools=[
            {"type": "function", "function": {"name": "terminal", "parameters": {"type": "object"}}},
            {"type": "function", "function": {"name": "read_file", "parameters": {"type": "object"}}},
            {"type": "function", "function": {"name": "search_files", "parameters": {"type": "object"}}},
            {"type": "function", "function": {"name": "web_search", "parameters": {"type": "object"}}},
            {"type": "function", "function": {"name": "web_extract", "parameters": {"type": "object"}}},
            {"type": "function", "function": {"name": "browser_navigate", "parameters": {"type": "object"}}},
            {"type": "function", "function": {"name": "gmail_search", "parameters": {"type": "object"}}},
            {"type": "function", "function": {"name": "calendar_availability", "parameters": {"type": "object"}}},
            {"type": "function", "function": {"name": "patch", "parameters": {"type": "object"}}},
            {"type": "function", "function": {"name": "write_file", "parameters": {"type": "object"}}},
        ],
        _memory_store=None,
        _memory_manager=_MemoryManager(),
        session_input_tokens=123,
        session_output_tokens=45,
        context_compressor=SimpleNamespace(last_compression_rough_tokens=1000, last_prompt_tokens=650),
    )


def test_classifier_expectations_for_phase_1_5_cases():
    cases = {
        "Summarise a long external article or PDF with citations.": "analysis_or_research",
        "Research a current competitor and summarise positioning.": "analysis_or_research",
        "Find current vendor pricing and compare feature differences.": "analysis_or_research",
        "Find current vendor pricing from one source.": "scoped_lookup",
        "Check calendar availability for next week.": "scoped_lookup",
        "Summarise my unread inbox.": "scoped_lookup",
        "Produce a daily priorities briefing from inbox, calendar, and tasks.": "analysis_or_research",
        "Apply the approved code patch and run focused tests.": "execution_task",
        "Investigate provider quota/auth failures and recommend fallback action.": "analysis_or_research",
        "Hey Hermes what's the weather like tomorrow?": "scoped_lookup",
        "What's the forecast for Cape Town tomorrow?": "scoped_lookup",
        "What is JSON?": "direct_answer",
    }
    for prompt, expected in cases.items():
        assert classify_request(prompt) == expected
        assert classify_request(prompt) == expected


def test_tool_budget_expectations_are_metadata_only():
    assert tool_budget_expectation("direct_answer")["range"] == "0-1"
    assert tool_budget_expectation("scoped_lookup")["range"] == "1-3"
    assert tool_budget_expectation("analysis_or_research")["range"] == "2-8"
    assert tool_budget_expectation("execution_task")["range"] == "task-dependent"
    assert tool_budget_expectation("deep_work")["range"] == "plan-and-checkpoints"
    assert all(tool_budget_expectation(cls)["metadata_only"] for cls in ("direct_answer", "scoped_lookup", "analysis_or_research", "execution_task", "deep_work"))


def test_error_classifier_identifies_required_classes():
    assert classify_error(status_code=429, message="rate limit exceeded") == "auth_or_quota"
    assert classify_error(status_code=401, message="invalid api key") == "auth_or_quota"
    assert classify_error(status_code=400, message="invalid JSON schema") == "configuration_or_schema"
    assert classify_error(message="tool unavailable: mcp server unavailable") == "tool_unavailable"
    assert classify_error(message="approval required before write") == "approval_required"
    assert classify_error(status_code=503, message="upstream timeout") == "transient"


def test_failure_policy_decisions_are_deterministic_and_non_looping():
    auth_with_fallback = decide_failure_policy("auth_or_quota", retry_count=2, max_retries=3, has_pending_fallback=True)
    assert auth_with_fallback["action"] == "activate_fallback"
    assert auth_with_fallback["retry_failed_provider"] is False
    assert auth_with_fallback["fallback_allowed"] is True

    auth_without_fallback = decide_failure_policy("auth_or_quota", retry_count=2, max_retries=3, has_pending_fallback=False)
    assert auth_without_fallback["action"] == "fail_closed"
    assert auth_without_fallback["retry_failed_provider"] is False
    assert auth_without_fallback["reason_code"] == "auth_or_quota_no_fallback"

    schema = decide_failure_policy("configuration_or_schema", retry_count=1, max_retries=3, has_pending_fallback=True)
    assert schema["action"] == "fail_closed"
    assert schema["fallback_allowed"] is False
    assert schema["retry_failed_provider"] is False

    approval = decide_failure_policy("approval_required")
    assert approval["action"] == "approval_required"
    assert approval["retry_failed_provider"] is False

    unavailable = decide_failure_policy("tool_unavailable")
    assert unavailable["action"] == "fail_closed"
    assert unavailable["reason_code"] == "tool_unavailable_no_safe_fallback"

    transient = decide_failure_policy("transient", retry_count=1, max_retries=3, has_pending_fallback=True)
    assert transient["action"] == "existing_retry"
    assert transient["retry_failed_provider"] is True
    assert transient["reason_code"] == "transient_existing_bounded_retry"
    assert decide_failure_policy("transient", retry_count=1, max_retries=3, has_pending_fallback=True) == transient


def test_feature_flag_defaults_off_and_env_enables(monkeypatch):
    monkeypatch.delenv("HERMES_INTELLIGENCE_POLICY", raising=False)
    monkeypatch.delenv("HERMES_INTELLIGENCE_MEMORY_POLICY", raising=False)
    monkeypatch.delenv("HERMES_INTELLIGENCE_FAILURE_POLICY", raising=False)
    assert intelligence_policy_enabled({"agent": {}}) is False
    assert intelligence_policy_enabled({"agent": {"intelligence_policy_enabled": True}}) is True
    assert intelligence_memory_policy_enabled({"agent": {}}) is False
    assert intelligence_memory_policy_enabled({"agent": {"intelligence_memory_policy_enabled": True}}) is True
    assert intelligence_tool_policy_enabled({"agent": {}}) is False
    assert intelligence_tool_policy_enabled({"agent": {"intelligence_tool_policy_enabled": True}}) is True
    assert intelligence_evidence_compaction_enabled({"agent": {}}) is False
    assert intelligence_evidence_compaction_enabled({"agent": {"intelligence_evidence_compaction_enabled": True}}) is True
    assert intelligence_failure_policy_enabled({"agent": {}}) is False
    assert intelligence_failure_policy_enabled({"agent": {"intelligence_failure_policy_enabled": True}}) is True
    assert memory_policy_config({"agent": {"intelligence_memory_token_budget": 80, "intelligence_memory_max_entries": 2}}) == {
        "memory_token_budget": 80,
        "max_memory_entries": 2,
    }
    assert tool_policy_config({"agent": {"intelligence_tool_policy_max_exposed_tools_per_group": 3}})["max_exposed_tools_per_group"] == 3
    assert evidence_compaction_config({"agent": {"intelligence_evidence_max_compacted_bytes": 1000}})["max_compacted_evidence_bytes"] == 1000
    monkeypatch.setenv("HERMES_INTELLIGENCE_POLICY", "1")
    assert intelligence_policy_enabled({"agent": {"intelligence_policy_enabled": False}}) is True
    monkeypatch.setenv("HERMES_INTELLIGENCE_FAILURE_POLICY", "1")
    assert intelligence_failure_policy_enabled({"agent": {"intelligence_failure_policy_enabled": False}}) is True


def test_feature_flag_off_produces_no_observer_or_report(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    agent = _agent(enabled=False)
    observer = start_run_observer(agent, user_message="Implement this", system_prompt="system", task_id="t1", turn_id="turn1")
    assert observer is None
    agent._policy_run_observer = observer
    assert finalize_run(agent, completed=True, failed=False) is None
    assert not (tmp_path / "run_reports" / "latest_policy_run.json").exists()


def test_report_captures_real_runtime_request_sizes(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    agent = _agent(enabled=True)
    observer = PolicyRunObserver.from_agent(
        agent,
        user_message="Research a current competitor",
        system_prompt="initial system prompt",
        task_id="t1",
        turn_id="turn1",
        ext_prefetch_cache="prefetched memory",
    )
    agent._policy_run_observer = observer
    api_kwargs = {
        "messages": [
            {"role": "system", "content": "actual runtime system prompt"},
            {"role": "user", "content": "actual runtime volatile context"},
        ],
        "tools": agent.tools,
    }
    record_runtime_request(agent, api_kwargs=api_kwargs)
    record_tool(agent, "read_file", failed=False)
    report = finalize_run(agent, completed=True, failed=False)

    assert report["request_class"] == "analysis_or_research"
    assert report["system_prompt_bytes"] == len("actual runtime system prompt".encode())
    assert report["estimated_prompt_tokens"] > 0
    assert report["tool_schema_bytes"] > 0
    assert report["tool_schema_estimated_tokens"] > 0
    assert report["volatile_context_bytes"] > 0
    assert report["volatile_context_estimated_tokens"] > 0
    assert report["runtime_request_bytes"] > report["volatile_context_bytes"]
    assert report["runtime_request_estimated_tokens"] > 0
    assert report["request_message_count"] == 2
    assert report["injected_memory_count"] == 2
    assert report["tools_exposed"] == [
        "browser_navigate",
        "calendar_availability",
        "gmail_search",
        "patch",
        "read_file",
        "search_files",
        "terminal",
        "web_extract",
        "web_search",
        "write_file",
    ]
    assert report["tools_called"] == ["read_file"]
    assert report["tool_attempts"] == 1
    assert report["tool_successes"] == 1
    assert report["compaction_savings_tokens"] == 350
    assert report["final_state"] == "completed"
    assert report["measurement_labels"]["runtime_request_bytes"] == "real_runtime_derived"
    assert report["tool_budget_expectation"]["range"] == "2-8"


def test_failure_policy_report_metadata_is_sanitized(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    agent = _agent(enabled=True)
    decision = decide_failure_policy("auth_or_quota", retry_count=1, max_retries=3, has_pending_fallback=True)
    decision["fallback_attempted"] = True
    decision["fallback_succeeded"] = True
    decision["raw_error_message"] = "api_key=secret-token quota exhausted"
    record_failure_policy_decision(agent, decision)
    observer = PolicyRunObserver.from_agent(
        agent,
        user_message="Investigate provider quota failure",
        system_prompt="system",
        task_id="t1",
        turn_id="turn1",
    )
    agent._policy_run_observer = observer
    report = finalize_run(agent, completed=False, failed=True)
    serialized = str(report)
    assert report["failure_policy_enabled"] is True
    assert report["failure_policy_error_class"] == "auth_or_quota"
    assert report["failure_policy_action"] == "activate_fallback"
    assert report["failure_policy_fallback_attempted"] is True
    assert report["failure_policy_fallback_succeeded"] is True
    assert report["measurement_labels"]["failure_policy"] == "runtime_error_derived"
    assert "secret-token" not in serialized


def test_observational_mode_does_not_mutate_runtime_selection_or_context(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    agent = _agent(enabled=True)
    before = {"provider": agent.provider, "model": agent.model, "api_mode": agent.api_mode, "tools": list(agent.tools)}
    observer = start_run_observer(agent, user_message="Audit the runtime", system_prompt="stable prompt", task_id="t1", turn_id="turn1")
    agent._policy_run_observer = observer
    report = finalize_run(agent, completed=False, failed=True)
    after = {"provider": agent.provider, "model": agent.model, "api_mode": agent.api_mode, "tools": list(agent.tools)}
    assert before == after
    assert report["final_state"] == "failed"


def test_memory_policy_required_decisions_are_deterministic():
    cases = {
        "What is JSON?": ("skipped", "generic_direct_answer"),
        "Research current vendor pricing.": ("skipped", "external_current_research"),
        "Recommend a vendor using my budget and preferences.": ("user", "user_constraints_relevant"),
        "Diagnose Hermes logs and runtime config.": ("project", "project_research_constraints"),
        "Summarise my inbox and calendar tasks.": ("user", "personal_lookup"),
        "Find the prior decision document in Drive.": ("project", "project_or_prior_lookup"),
        "Use this secret API key memory.": ("skipped", "sensitive_or_private_memory_risk"),
    }
    for prompt, expected in cases.items():
        assert decide_memory_injection(prompt) == expected
        assert decide_memory_injection(prompt) == expected


def test_memory_policy_flag_off_preserves_prefetched_memory():
    agent = SimpleNamespace(
        _intelligence_memory_policy_enabled=False,
        _intelligence_memory_policy_config={"memory_token_budget": 1, "max_memory_entries": 1},
        _intelligence_memory_policy_last_decision=None,
    )
    memory = "line one\nline two\nline three"
    assert apply_memory_policy(agent, user_message="What is JSON?", prefetched_memory=memory) == memory
    assert agent._intelligence_memory_policy_last_decision["decision"] == "disabled"
    assert agent._intelligence_memory_policy_last_decision["estimated_tokens_before"] == agent._intelligence_memory_policy_last_decision["estimated_tokens_after"]


def test_memory_policy_reduces_irrelevant_memory_without_touching_runtime_selection():
    agent = SimpleNamespace(
        _intelligence_memory_policy_enabled=True,
        _intelligence_memory_policy_config={"memory_token_budget": 8, "max_memory_entries": 1},
        _intelligence_memory_policy_last_decision=None,
        provider="custom",
        model="mock-runtime/model",
        api_mode="openai",
        tools=[{"type": "function", "function": {"name": "read_file"}}],
    )
    before = {"provider": agent.provider, "model": agent.model, "api_mode": agent.api_mode, "tools": list(agent.tools)}
    memory = "private project note\nanother private note"
    filtered = apply_memory_policy(agent, user_message="What is JSON?", prefetched_memory=memory)
    after = {"provider": agent.provider, "model": agent.model, "api_mode": agent.api_mode, "tools": list(agent.tools)}
    assert filtered == ""
    assert before == after
    assert agent._intelligence_memory_policy_last_decision["decision"] == "skipped"
    assert agent._intelligence_memory_policy_last_decision["estimated_savings"] > 0


def test_memory_policy_caps_relevant_memory_and_keeps_reports_sanitized(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    agent = _agent(enabled=True)
    agent._intelligence_memory_policy_enabled = True
    agent._intelligence_memory_policy_config = {"memory_token_budget": 8, "max_memory_entries": 1}
    raw_memory = "secret customer token abc123 should not appear\nHermes prior decision path"
    filtered = apply_memory_policy(agent, user_message="Find the prior Hermes decision document", prefetched_memory=raw_memory)
    observer = PolicyRunObserver.from_agent(
        agent,
        user_message="Find the prior Hermes decision document",
        system_prompt="system",
        task_id="t1",
        turn_id="turn1",
        ext_prefetch_cache=filtered,
    )
    agent._policy_run_observer = observer
    report = finalize_run(agent, completed=True, failed=False)
    serialized = str(report)
    assert report["memory_policy_enabled"] is True
    assert report["memory_decision"] == "project"
    assert report["memory_entries_considered"] == 2
    assert report["memory_entries_injected"] == 1
    assert report["memory_estimated_savings"] > 0
    assert "abc123" not in serialized
    assert "secret customer token" not in serialized


def test_tool_policy_required_exposure_groups_are_deterministic():
    cases = {
        "What is JSON?": "none",
        "Research current vendor pricing from web sources.": "research",
        "Check calendar availability tomorrow.": "personal_readonly",
        "Summarise my inbox.": "personal_readonly",
        "Find the prior decision document in Drive.": "workspace_readonly",
        "Diagnose Hermes logs and runtime config.": "engineering_readonly",
        "Apply the approved code patch.": "engineering_execution",
        "Review this config file in read-only mode.": "workspace_readonly",
        "Use the mystery connector tool.": "full_current_default",
        "Hey Hermes what's the weather like tomorrow?": "research",
        "What's the forecast for Cape Town tomorrow?": "research",
    }
    for prompt, expected in cases.items():
        assert decide_tool_exposure_group(prompt)[0] == expected


def test_tool_policy_flag_off_preserves_tool_exposure_exactly():
    agent = _agent(enabled=True)
    agent._intelligence_tool_policy_enabled = False
    api_kwargs = {"tools": list(agent.tools)}
    filtered = apply_tool_policy(agent, user_message="What is JSON?", api_kwargs=api_kwargs)
    assert filtered["tools"] == api_kwargs["tools"]
    assert agent._intelligence_tool_policy_last_decision["group"] == "disabled"
    assert agent._intelligence_tool_policy_last_decision["schema_bytes_before"] == agent._intelligence_tool_policy_last_decision["schema_bytes_after"]


def test_tool_policy_filters_direct_research_personal_and_engineering_groups():
    agent = _agent(enabled=True)
    agent._intelligence_tool_policy_enabled = True
    agent._intelligence_tool_policy_config = {"max_exposed_tools_per_group": 12, "exclude_write_tools_unless_approved": True}

    direct = apply_tool_policy(agent, user_message="What is JSON?", api_kwargs={"tools": list(agent.tools)})
    assert direct["tools"] == []
    assert agent._intelligence_tool_policy_last_decision["group"] == "none"

    research = apply_tool_policy(agent, user_message="Research current pricing on the web.", api_kwargs={"tools": list(agent.tools)})
    research_names = [tool["function"]["name"] for tool in research["tools"]]
    assert research_names == ["web_search", "web_extract", "browser_navigate"]
    assert "gmail_search" not in research_names
    assert "patch" not in research_names

    weather = apply_tool_policy(agent, user_message="Hey Hermes what's the weather like tomorrow?", api_kwargs={"tools": list(agent.tools)})
    weather_names = [tool["function"]["name"] for tool in weather["tools"]]
    assert "web_search" in weather_names
    assert "gmail_search" not in weather_names
    assert "patch" not in weather_names

    personal = apply_tool_policy(agent, user_message="Check calendar availability.", api_kwargs={"tools": list(agent.tools)})
    personal_names = [tool["function"]["name"] for tool in personal["tools"]]
    assert personal_names == ["gmail_search", "calendar_availability"]

    eng = apply_tool_policy(agent, user_message="Diagnose Hermes logs read-only.", api_kwargs={"tools": list(agent.tools)})
    eng_names = [tool["function"]["name"] for tool in eng["tools"]]
    assert "read_file" in eng_names
    assert "search_files" in eng_names
    assert "patch" not in eng_names
    assert "write_file" not in eng_names
    assert agent._intelligence_tool_policy_last_decision["write_capable_tools_excluded"] is True


def test_tool_policy_execution_requires_approval_and_unknown_falls_back():
    agent = _agent(enabled=True)
    agent._intelligence_tool_policy_enabled = True
    agent._intelligence_tool_policy_config = {"max_exposed_tools_per_group": 12, "exclude_write_tools_unless_approved": True}

    approved = apply_tool_policy(agent, user_message="Apply the approved code patch.", api_kwargs={"tools": list(agent.tools)})
    approved_names = [tool["function"]["name"] for tool in approved["tools"]]
    assert "patch" in approved_names
    assert "write_file" in approved_names
    assert agent._intelligence_tool_policy_last_decision["group"] == "engineering_execution"

    unknown = apply_tool_policy(agent, user_message="Use the mystery connector tool.", api_kwargs={"tools": list(agent.tools)})
    assert len(unknown["tools"]) == len(agent.tools)
    assert agent._intelligence_tool_policy_last_decision["group"] == "full_current_default"
    assert agent._intelligence_tool_policy_last_decision["fallback_reason"] == "unknown_tool_or_connector"
    assert agent._intelligence_tool_policy_last_decision["mcp_started_during_request_preparation"] is False


def test_tool_policy_report_captures_schema_savings(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    agent = _agent(enabled=True)
    agent._intelligence_tool_policy_enabled = True
    agent._intelligence_tool_policy_config = {"max_exposed_tools_per_group": 12}
    observer = PolicyRunObserver.from_agent(
        agent,
        user_message="What is JSON?",
        system_prompt="system",
        task_id="t1",
        turn_id="turn1",
    )
    agent._policy_run_observer = observer
    filtered = apply_tool_policy(agent, user_message="What is JSON?", api_kwargs={"messages": [{"role": "system", "content": "system"}], "tools": list(agent.tools)})
    record_runtime_request(agent, api_kwargs=filtered)
    report = finalize_run(agent, completed=True, failed=False)
    assert report["tool_policy_enabled"] is True
    assert report["tool_exposure_group"] == "none"
    assert report["tools_available_before_policy"] == len(agent.tools)
    assert report["tools_exposed_after_policy"] == 0
    assert report["tool_schema_bytes_before_policy"] > report["tool_schema_bytes_after_policy"]
    assert report["tool_schema_estimated_token_savings"] > 0


def _evidence_agent(tmp_path=None, *, enabled=True, spill=False):
    return SimpleNamespace(
        _intelligence_evidence_compaction_enabled=enabled,
        _intelligence_evidence_compaction_config={
            "max_compacted_evidence_bytes": 1800,
            "max_retained_error_lines": 8,
            "max_retained_log_lines": 12,
            "enable_raw_output_references": spill,
            "redact_secrets_before_spill": True,
            "raw_output_spill_dir": str(tmp_path) if tmp_path else "",
            "fallback_to_raw_on_compaction_failure": True,
        },
        _intelligence_evidence_compaction_stats=None,
    )


def test_evidence_compaction_feature_flag_off_preserves_raw_output():
    agent = _evidence_agent(enabled=False)
    raw = "line\n" * 100
    assert compact_tool_result(agent, tool_name="terminal", result=raw) == raw


def test_repetitive_logs_compact_and_preserve_errors():
    agent = _evidence_agent()
    raw = "\n".join(["INFO heartbeat ok"] * 80 + ["2026-07-09 10:00:00 ERROR failed at /tmp/app.py:42"])
    compacted = compact_tool_result(agent, tool_name="terminal", result=raw)
    assert "[compact_tool_evidence]" in compacted
    assert "type: logs" in compacted
    assert "/tmp/app.py:42" in compacted
    assert "duplicate line" in compacted
    assert len(compacted) < len(raw)


def test_error_trace_preserves_stack_frame_path_line_and_message():
    agent = _evidence_agent()
    raw = "Traceback\n  File \"/repo/app.py\", line 17, in run\nValueError: bad config\n" + ("noise\n" * 50)
    compacted = compact_tool_result(agent, tool_name="execute_code", result=raw)
    assert "type: error" in compacted
    assert "/repo/app.py" in compacted
    assert "line 17" in compacted
    assert "ValueError" in compacted


def test_json_payload_compaction_preserves_ids_status_timestamps_and_errors():
    agent = _evidence_agent()
    raw = '{"id":"run_123","status":"failed","timestamp":"2026-07-09T10:00:00Z","data":"' + ("x" * 2000) + '","error":"schema mismatch"}'
    compacted = compact_tool_result(agent, tool_name="api_tool", result=raw)
    assert "run_123" in compacted
    assert "failed" in compacted
    assert "2026-07-09T10:00:00Z" in compacted
    assert "schema mismatch" in compacted


def test_web_file_and_connector_outputs_preserve_key_evidence_without_raw_private_body():
    web_agent = _evidence_agent()
    web = "Title: Vendor Pricing\nSource: https://example.com\nDate: 2026-07-09\nClaim: price changed\nCitation: [1]\n" + ("boilerplate\n" * 80)
    web_compacted = compact_tool_result(web_agent, tool_name="browser_snapshot", result=web)
    assert "Title: Vendor Pricing" in web_compacted
    assert "https://example.com" in web_compacted
    assert "Citation" in web_compacted

    file_agent = _evidence_agent()
    file_text = "/repo/a.py:12 def run():\n/repo/a.py:13 raise ValueError('x')\n" + ("unrelated\n" * 80)
    file_compacted = compact_tool_result(file_agent, tool_name="read_file", result=file_text)
    assert "/repo/a.py:12" in file_compacted
    assert "ValueError" in file_compacted

    conn_agent = _evidence_agent()
    connector = "Email id: msg_1\nFrom: a@example.com\nSubject: Renewal\nBody: very private body " + ("secret details " * 100)
    conn_compacted = compact_tool_result(conn_agent, tool_name="gmail_search", result=connector)
    assert "msg_1" in conn_compacted
    assert "Subject: Renewal" in conn_compacted
    assert "secret details secret details secret details" not in conn_compacted


def test_redaction_and_spill_reference_are_safe(tmp_path):
    agent = _evidence_agent(tmp_path, spill=True)
    raw = "api_key=sk-abcdefghijklmnopqrstuvwxyz\n" + ("log line\n" * 500)
    compacted = compact_tool_result(agent, tool_name="terminal", result=raw)
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in compacted
    assert "raw_ref:" in compacted
    stats = agent._intelligence_evidence_compaction_stats
    assert stats["raw_outputs_spilled_count"] == 1
    assert stats["redaction_count"] > 0
    spill_files = [path for path in tmp_path.iterdir() if path.is_file()]
    assert spill_files
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in spill_files[0].read_text()


def test_compaction_failure_falls_back_to_raw(monkeypatch):
    agent = _evidence_agent()
    raw = "important raw output"
    monkeypatch.setattr("agent.intelligence_policy._summarize_evidence", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert compact_tool_result(agent, tool_name="terminal", result=raw) == raw
    assert agent._intelligence_evidence_compaction_stats["fallback_to_raw_count"] == 1


def test_phase5_failure_classifier_evidence_survives_compaction():
    agent = _evidence_agent()
    raw = "\n".join(
        [
            "provider=openrouter model=anthropic/claude-sonnet-4",
            "HTTP 429 Too Many Requests",
            "quota exceeded and invalid auth token",
            "timeout marker: request timed out after 60s",
            "schema/configuration error: missing required field tools[0].function.name",
            "tool: web_search",
            "Traceback (most recent call last):",
            "  File \"/repo/agent/provider.py\", line 88, in call_provider",
            "RuntimeError: approval required before write action",
        ]
        + ["low signal line"] * 120
    )
    compacted = compact_tool_result(agent, tool_name="web_search", result=raw)
    required_fragments = [
        "HTTP 429",
        "openrouter",
        "anthropic/claude-sonnet-4",
        "quota",
        "auth",
        "timed out",
        "schema/configuration error",
        "tool: web_search",
        "/repo/agent/provider.py",
        "line 88",
        "approval required",
    ]
    for fragment in required_fragments:
        assert fragment in compacted


def test_evidence_report_has_no_raw_secret_and_preserves_prior_policy_fields(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    agent = _agent(enabled=True)
    agent._intelligence_evidence_compaction_enabled = True
    agent._intelligence_evidence_compaction_config = _evidence_agent()._intelligence_evidence_compaction_config
    agent._intelligence_memory_policy_last_decision = {
        "enabled": True,
        "decision": "skipped",
        "entries_considered": 1,
        "entries_injected": 0,
        "estimated_tokens_before": 10,
        "estimated_tokens_after": 0,
        "estimated_savings": 10,
        "reason_code": "generic_direct_answer",
    }
    agent._intelligence_tool_policy_last_decision = {
        "enabled": True,
        "group": "none",
        "tools_before": 8,
        "tools_after": 0,
        "schema_bytes_before": 1000,
        "schema_bytes_after": 2,
        "schema_token_savings": 250,
        "omitted_tool_categories": ["engineering_execution"],
        "fallback_reason": "",
        "write_capable_tools_excluded": True,
        "mcp_started_during_request_preparation": False,
    }
    compact_tool_result(agent, tool_name="terminal", result="password=supersecret123\n" + ("noise\n" * 200))
    observer = PolicyRunObserver.from_agent(agent, user_message="What is JSON?", system_prompt="system", task_id="t1", turn_id="turn1")
    agent._policy_run_observer = observer
    report = finalize_run(agent, completed=True, failed=False)
    serialized = str(report)
    assert report["evidence_compaction_enabled"] is True
    assert report["tool_results_compacted_count"] == 1
    assert report["memory_decision"] == "skipped"
    assert report["tool_exposure_group"] == "none"
    assert "supersecret123" not in serialized
