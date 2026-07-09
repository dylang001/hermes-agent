from __future__ import annotations

from gateway.config import Platform
from gateway.run import _prepare_gateway_status_message, _sanitize_gateway_final_response
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
    assert result == "Found a stale memory/source conflict. I am verifying against live config before touching anything."


def test_telegram_details_request_preserves_expanded_output(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    text = "Full report:\n" + "\n".join(f"detail line {i}" for i in range(30))
    assert _sanitize_gateway_final_response(Platform.TELEGRAM, text) == text


def test_non_telegram_surfaces_are_unchanged(monkeypatch):
    monkeypatch.setenv("HERMES_TELEGRAM_CONCISE_RESPONSES", "1")
    text = "Validation completed.\n" + "\n".join(f"detail line {i}" for i in range(40))
    assert _sanitize_gateway_final_response(Platform.LOCAL, text) == text
