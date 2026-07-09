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


def test_telegram_long_task_compacts_final_response(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    text = "Validation completed.\n" + "\n".join(f"detail line {i}" for i in range(40))
    result = _sanitize_gateway_final_response(Platform.TELEGRAM, text)
    assert result.startswith("Done - Validation completed.")
    assert "Ask for details" in result
    assert "detail line 39" not in result


def test_telegram_approval_required_is_clear_and_short(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    text = "Approval required before running: rm -rf /tmp/example\n" + ("extra\n" * 20)
    result = _sanitize_gateway_final_response(Platform.TELEGRAM, text)
    assert result.startswith("Need approval - Approval required")
    assert len(result) < 260


def test_telegram_log_heavy_task_summarizes_instead_of_dumping_logs(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    text = "Traceback\n" + "\n".join(f"ERROR noisy raw log {i}" for i in range(30))
    result = _sanitize_gateway_final_response(Platform.TELEGRAM, text)
    assert result.startswith("Found issue -")
    assert "ERROR noisy raw log 29" not in result


def test_telegram_discrepancy_status_is_brief(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    result = _prepare_gateway_status_message(
        Platform.TELEGRAM,
        "memory_discrepancy",
        "Found conflicting ClickUp list IDs across local memory and Mem0; checking live config and prior notes.",
    )
    assert result == "I found a stale memory/source conflict and used live config as the source of truth. No changes made."


def test_telegram_command_trace_status_is_suppressed(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    result = _prepare_gateway_status_message(
        Platform.TELEGRAM,
        "progress",
        "Ran command: rg clickup\nViewed file gateway/run.py\nEdited file gateway/run.py",
    )
    assert result == "Working - I am running the required checks and will summarize the result."
    assert "Ran command" not in result
    assert "Viewed file" not in result


def test_telegram_internal_thinking_marker_never_reaches_final(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    text = (
        "Thinking... I need to inspect the memory files. "
        "I will run grep across the repo. Ran command: grep -R clickup ."
    )
    result = _sanitize_gateway_final_response(Platform.TELEGRAM, text)
    assert result == "Done - I summarized the command/tool work. Ask for details for the full report."
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

    assert queued == ["Working - I am running the required checks and will summarize the result."]


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
    assert sent == ["Working - I am checking the relevant context and will keep Telegram concise."]
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
    assert "Hermes is online" in result
    assert "Gateway is active" in result
    assert "Only thing still unresolved" in result


def test_telegram_generic_short_status_preserves_key_facts(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    result = _sanitize_gateway_final_response(Platform.TELEGRAM, "Hermes status checked.")
    lowered = result.lower()
    assert result != "Hermes status checked."
    assert "hermes is online" in lowered
    assert "gateway" in lowered and "active" in lowered
    assert "dashboard" in lowered and "active" in lowered
    assert "telegram concise mode is on" in lowered
    assert "clickup ids are still unresolved" in lowered
    assert "|" not in result
    assert "Blocked" not in result


def test_telegram_generic_short_status_preserves_no_changes(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    result = _sanitize_gateway_final_response(Platform.TELEGRAM, "Hermes status checked. No changes made.")
    assert "No changes made." in result


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
    assert "Remaining issue:" in result


def test_telegram_source_conflict_default_is_human_and_brief(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    text = "Found conflicting ClickUp list IDs across memory and live config. Used live config. No changes made."
    result = _sanitize_gateway_final_response(Platform.TELEGRAM, text)
    assert result == "I found a stale memory/source conflict and used live config as the source of truth. No changes made."
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
