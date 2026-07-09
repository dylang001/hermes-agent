from __future__ import annotations

from types import SimpleNamespace

import pytest

from gateway.config import Platform
from gateway.run import _prepare_gateway_status_message, _sanitize_gateway_final_response
from gateway.stream_consumer import GatewayStreamConsumer
from gateway.stream_dispatch import GatewayEventDispatcher
from gateway.stream_events import ToolCallChunk
from gateway.telegram_response_policy import apply_telegram_response_policy


def test_telegram_policy_disabled_by_default_preserves_output(monkeypatch):
    monkeypatch.delenv("HERMES_TELEGRAM_CONCISE_RESPONSES", raising=False)
    text = "Line one\n" + ("raw log line\n" * 20)
    assert apply_telegram_response_policy(Platform.TELEGRAM, text) == text


def test_telegram_direct_answer_stays_short_when_enabled(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    text = "JSON is a text format for structured data."
    assert _sanitize_gateway_final_response(Platform.TELEGRAM, text) == text


def test_telegram_long_final_response_preserves_agent_output(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    text = "Validation completed.\n" + "\n".join(f"detail line {i}" for i in range(40))
    result = _sanitize_gateway_final_response(Platform.TELEGRAM, text)
    assert result == text


def test_telegram_approval_required_is_clear_and_short(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    text = "Approval required before running: rm -rf /tmp/example\n" + ("extra\n" * 20)
    result = _sanitize_gateway_final_response(Platform.TELEGRAM, text)
    assert result.startswith("Need approval - Approval required")
    assert len(result) < 260


def test_telegram_log_heavy_final_preserves_agent_output(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    text = "Traceback\n" + "\n".join(f"ERROR noisy raw log {i}" for i in range(30))
    result = _sanitize_gateway_final_response(Platform.TELEGRAM, text)
    assert result == text


def test_telegram_discrepancy_status_is_brief(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    result = _prepare_gateway_status_message(
        Platform.TELEGRAM,
        "memory_discrepancy",
        "Found conflicting ClickUp list IDs across local memory and Mem0; checking live config and prior notes.",
    )
    assert result == "Found conflicting ClickUp list IDs across local memory and Mem0; checking live config and prior notes."


def test_telegram_command_trace_status_is_suppressed(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    result = _prepare_gateway_status_message(
        Platform.TELEGRAM,
        "progress",
        "Ran command: rg clickup\nViewed file gateway/run.py\nEdited file gateway/run.py",
    )
    assert result == "Working on it. I’ll keep the update short."
    assert "Ran command" not in result
    assert "Viewed file" not in result


def test_telegram_internal_thinking_marker_never_reaches_final(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    text = (
        "Thinking... I need to inspect the memory files. "
        "I will run grep across the repo. Ran command: grep -R clickup ."
    )
    result = _sanitize_gateway_final_response(Platform.TELEGRAM, text)
    assert result == "Done. I summarized the work. Ask for details if you want the full trace."
    assert "Thinking" not in result
    assert "grep -R" not in result


def test_telegram_tool_trace_dispatch_is_summarized(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")

    class Adapter:
        platform = Platform.TELEGRAM

        def format_tool_event(self, event, *, mode="all", preview_max_len=40):
            return f"Tool call: {event.tool_name} {event.preview}"

    queued = []
    dispatcher = GatewayEventDispatcher(Adapter(), enqueue_tool_line=queued.append)
    dispatcher.dispatch(ToolCallChunk(tool_name="terminal", preview="cat /var/log/hermes.log"))

    assert queued == ["Working on it. I’ll keep the update short."]


@pytest.mark.asyncio
async def test_telegram_stream_commentary_trace_is_summarized(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    sent = []

    class Adapter:
        platform = Platform.TELEGRAM

        async def send(self, chat_id, content, reply_to=None, metadata=None):
            sent.append(content)
            return SimpleNamespace(success=True, message_id="m1")

    consumer = GatewayStreamConsumer(Adapter(), "chat")
    ok = await consumer._send_commentary("I'll inspect the repo first, then run rg over the files.")

    assert ok is True
    assert sent == ["Working on it. I’ll keep the update short."]
    assert "I'll inspect" not in sent[0]


@pytest.mark.asyncio
async def test_non_telegram_stream_commentary_is_unchanged(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    sent = []

    class Adapter:
        platform = Platform.LOCAL

        async def send(self, chat_id, content, reply_to=None, metadata=None):
            sent.append(content)
            return SimpleNamespace(success=True, message_id="m1")

    consumer = GatewayStreamConsumer(Adapter(), "chat")
    text = "I'll inspect the repo first, then run rg over the files."
    ok = await consumer._send_commentary(text)

    assert ok is True
    assert sent == [text]


def test_telegram_details_request_preserves_expanded_output(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    text = "Full report:\n" + "\n".join(f"detail line {i}" for i in range(30))
    result = _sanitize_gateway_final_response(Platform.TELEGRAM, text)
    assert result.startswith("Full report:")
    assert "detail line 0" in result
    assert "detail line 6" in result


def test_telegram_short_status_must_not_be_blocked_or_table(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    text = """Blocked - Hermes — short status (read-only check, nothing touched)
| Area | State | Note |
| --- | --- | --- |
| Gateway | active | healthy |
| Dashboard | active | healthy |
| Telegram concise mode | enabled | ok |
| ClickUp | unresolved | canonical list ID missing |
Generated: today
Operator: Hermes
Reviewer: Dylan
"""
    result = _sanitize_gateway_final_response(Platform.TELEGRAM, text)
    assert "Blocked" not in result
    assert "|" not in result
    assert "Generated:" not in result
    assert "Operator" not in result
    assert "Reviewer" not in result
    assert "Gateway: active" in result
    assert "Dashboard: active" in result
    assert "ClickUp: unresolved" in result


def test_telegram_generic_short_status_is_not_replaced_with_canned_facts(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    result = _sanitize_gateway_final_response(Platform.TELEGRAM, "Hermes status checked.")
    assert result == "Hermes status checked."
    assert "|" not in result
    assert "Blocked" not in result


def test_telegram_generic_short_status_preserves_no_changes(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    result = _sanitize_gateway_final_response(Platform.TELEGRAM, "Hermes status checked. No changes made.")
    assert result == "Hermes status checked. No changes made."


def test_telegram_unrelated_answer_is_not_replaced_by_status_template(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    text = "The API key rotation window is tomorrow. Hermes status checked."
    result = _sanitize_gateway_final_response(Platform.TELEGRAM, text)
    assert result == text
    assert "Gateway and dashboard" not in result
    assert "ClickUp IDs" not in result


def test_telegram_weather_answer_is_not_rewritten_to_fake_summary(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    text = (
        "I need your location to check tomorrow's weather. "
        "Send a city or share your Telegram location and I’ll look it up."
    )
    result = _sanitize_gateway_final_response(Platform.TELEGRAM, text)
    assert result == text
    assert not result.startswith("Summary:")
    assert "Ask for details" not in result


def test_telegram_full_report_expands_without_wrong_approval(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    text = """Need approval - # Hermes — Full Status Report Generated
Generated: 2026-07-09
Operator: Hermes
Reviewer: Dylan
| Area | State | Note |
| --- | --- | --- |
| Gateway | active | healthy |
| Dashboard | active | healthy |
| Telegram concise mode | enabled | ok |
| Observability | enabled | ok |
| Memory/tool/evidence/failure policies | enabled | ok |
| MCP children | Exa + Obsidian only | no Zoho child |
| Canonical context | installed | ok |
| ClickUp | unresolved | workspace reference found, verified list ID missing |
No files or memory were changed during this read-only check.
"""
    result = _sanitize_gateway_final_response(Platform.TELEGRAM, text)
    assert result.startswith("Full report:")
    assert "Need approval" not in result
    assert "Blocked" not in result
    assert "Generated:" not in result
    assert "Operator" not in result
    assert "Reviewer" not in result
    assert "|" not in result
    assert "Gateway: active" in result
    assert "Dashboard: active" in result
    assert "Memory/tool/evidence/failure policies: enabled" in result
    assert "MCP children: Exa + Obsidian only" in result
    assert "ClickUp: unresolved" in result


def test_telegram_full_report_uses_canonical_clickup_when_resolved(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    text = (
        "Full report:\n"
        "Hermes active\n"
        "Gateway active\n"
        "Dashboard active\n"
        "Telegram concise mode enabled\n"
        "Memory/tool/evidence/failure policies enabled\n"
        "MCP children Exa + Obsidian only\n"
        "Canonical context installed\n"
        "ClickUp IDs canonical\n"
        "No files or memory were changed during this check."
    )
    result = _sanitize_gateway_final_response(Platform.TELEGRAM, text)
    assert "ClickUp IDs canonical" in result
    assert "Remaining issue:" not in result
    assert "not canonical" not in result


def test_telegram_source_conflict_default_is_human_and_brief(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    text = "Found conflicting ClickUp list IDs across memory and live config. Used live config. No changes made."
    result = _sanitize_gateway_final_response(Platform.TELEGRAM, text)
    assert result == text
    assert "discrepancy report" not in result.lower()


def test_telegram_actual_approval_still_uses_need_approval(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    text = "Approval required before archive stale worktrees under /root/.hermes/worktrees."
    result = _sanitize_gateway_final_response(Platform.TELEGRAM, text)
    assert result.startswith("Need approval - Approval required before archive stale worktrees")


def test_non_telegram_surfaces_are_unchanged(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    text = "Validation completed.\n" + "\n".join(f"detail line {i}" for i in range(40))
    assert _sanitize_gateway_final_response(Platform.LOCAL, text) == text
