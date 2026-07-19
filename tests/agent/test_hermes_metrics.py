"""Observatory Phase 1 — metrics registry + loopback server."""

from __future__ import annotations

import socket
import time
import urllib.request

import pytest

from agent import hermes_metrics as hm


@pytest.fixture(autouse=True)
def _clean_metrics():
    hm.reset_for_tests()
    yield
    hm.reset_for_tests()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_disabled_record_is_noop():
    hm.record_gateway_turn(success=True, duration_seconds=1.0)
    text = hm.render_metrics()
    assert "hermes_gateway_turns_total" not in text


def test_enabled_counters_and_histogram():
    port = _free_port()
    hm.start_metrics_server(enabled=True, bind_host="127.0.0.1", port=port)
    try:
        hm.record_gateway_turn(success=True, duration_seconds=0.25)
        hm.record_gateway_turn(success=False, duration_seconds=1.5)
        hm.record_model_call(success=True, duration_seconds=0.8)
        hm.record_tool_call(category="terminal", success=True, duration_seconds=0.05)
        hm.record_compression(kind="auto")
        hm.record_governor_event(kind="compact", live_tokens=12000)
        hm.record_token_usage(
            prompt_tokens=1000,
            completion_tokens=50,
            cache_read_tokens=900,
            cache_write_tokens=10,
        )
        hm.record_error(kind="api")

        text = hm.render_metrics()
        assert 'hermes_gateway_turns_total{outcome="success"} 1' in text
        assert 'hermes_gateway_turns_total{outcome="failure"} 1' in text
        assert "hermes_gateway_turn_duration_seconds_count" in text
        assert 'hermes_model_calls_total{status="ok"} 1' in text
        assert 'hermes_tool_calls_total{category="terminal",status="ok"} 1' in text
        assert 'hermes_compression_total{kind="auto"} 1' in text
        assert 'hermes_context_governor_events_total{kind="compact"} 1' in text
        assert "hermes_context_live_tokens 12000.000" in text
        assert "hermes_tokens_cache_read_total 900" in text
        assert 'hermes_errors_total{kind="api"} 1' in text

        # No sensitive payloads
        assert "password" not in text.lower()
        assert "api_key" not in text.lower()
        assert "Hello" not in text
    finally:
        hm.stop_metrics_server()


def test_tool_category_does_not_emit_raw_mcp_names():
    assert hm.tool_category("terminal") == "terminal"
    assert hm.tool_category("browser_navigate") == "browser"
    assert hm.tool_category("mcp_gmail__send") == "mcp"
    assert hm.tool_category("some_weird_skill_tool") == "other"


def test_refuses_non_loopback_bind():
    assert hm.start_metrics_server(enabled=True, bind_host="0.0.0.0", port=19109) is False
    assert hm.is_enabled() is False


def test_loopback_http_serves_metrics():
    port = _free_port()
    assert hm.start_metrics_server(enabled=True, bind_host="127.0.0.1", port=port)
    try:
        hm.record_gateway_turn(success=True, duration_seconds=0.1)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2) as resp:
            body = resp.read().decode("utf-8")
            assert resp.status == 200
            assert "hermes_gateway_turns_total" in body
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as resp:
            assert resp.read() == b"ok\n"
    finally:
        hm.stop_metrics_server()


def test_record_helpers_never_raise_when_broken(monkeypatch):
    hm.start_metrics_server(enabled=True, bind_host="127.0.0.1", port=_free_port())

    def _boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(hm._registry, "inc", _boom)
    # Must not raise into caller
    hm.record_gateway_turn(success=True, duration_seconds=1.0)
    hm.record_tool_call(category="file", success=True, duration_seconds=0.01)
    hm.stop_metrics_server()


def test_record_overhead_is_negligible():
    """Fail-open hot path should stay well under 50µs/call when disabled."""
    # Disabled path
    t0 = time.perf_counter()
    for _ in range(10_000):
        hm.record_gateway_turn(success=True, duration_seconds=0.01)
    disabled_per = (time.perf_counter() - t0) / 10_000

    hm.start_metrics_server(enabled=True, bind_host="127.0.0.1", port=_free_port())
    try:
        t0 = time.perf_counter()
        for _ in range(10_000):
            hm.record_gateway_turn(success=True, duration_seconds=0.01)
        enabled_per = (time.perf_counter() - t0) / 10_000
    finally:
        hm.stop_metrics_server()

    # Generous CI-safe ceilings (wall-clock, not a microbench lab).
    assert disabled_per < 5e-5, f"disabled path too slow: {disabled_per:.6f}s"
    assert enabled_per < 2e-4, f"enabled path too slow: {enabled_per:.6f}s"
    # Surface measured overhead for the Phase 1 report (printed under -s).
    print(
        f"\nobservatory_overhead disabled={disabled_per*1e6:.2f}µs/call "
        f"enabled={enabled_per*1e6:.2f}µs/call"
    )


def test_metrics_do_not_affect_normal_execution_import_side():
    """Importing / recording must not mutate agent conversation helpers."""
    from agent.context_governor import govern_request, ContextGovernorConfig

    hm.start_metrics_server(enabled=True, bind_host="127.0.0.1", port=_free_port())
    try:
        before = govern_request(
            [{"role": "user", "content": "hi"}],
            config=ContextGovernorConfig(enabled=False),
        )
        hm.record_governor_event(kind="pass", live_tokens=1)
        after = govern_request(
            [{"role": "user", "content": "hi"}],
            config=ContextGovernorConfig(enabled=False),
        )
        assert before.messages == after.messages
        assert before.blocked is False and after.blocked is False
    finally:
        hm.stop_metrics_server()
