"""Provider-agnostic usage telemetry: nulls, sources, and shared schema."""

from __future__ import annotations

from types import SimpleNamespace

from agent.usage_pricing import (
    CanonicalUsage,
    build_usage_telemetry_record,
    estimate_usage_cost,
    normalize_usage,
)


def test_complete_usage_metadata_marks_reported_fields():
    usage = SimpleNamespace(
        prompt_tokens=100,
        completion_tokens=20,
        prompt_tokens_details=SimpleNamespace(cached_tokens=40, cache_write_tokens=10),
        completion_tokens_details=SimpleNamespace(reasoning_tokens=5),
    )
    cu = normalize_usage(usage, provider="nvidia", api_mode="chat_completions")
    assert cu.usage_source == "provider_reported"
    assert cu.usage_confidence == "high"
    assert cu.input_tokens == 50
    assert cu.output_tokens == 20
    assert cu.cache_read_tokens == 40
    assert cu.cache_write_tokens == 10
    assert cu.reasoning_tokens == 5
    assert cu.raw_usage is not None
    record = build_usage_telemetry_record(
        cu, provider="nvidia", model="nvidia/nemotron-3-super-120b-a12b"
    )
    assert record["input_tokens"] == 50
    assert record["cache_read_tokens"] == 40
    assert record["reasoning_tokens"] == 5
    assert record["usage_source"] == "provider_reported"


def test_no_usage_metadata_is_unavailable_not_zero_filled_telemetry():
    cu = normalize_usage(None, provider="nvidia", api_mode="chat_completions")
    assert cu.usage_source == "unavailable"
    assert cu.reported_fields == frozenset()
    record = build_usage_telemetry_record(cu, provider="nvidia", model="x")
    assert record["input_tokens"] is None
    assert record["output_tokens"] is None
    assert record["cache_read_tokens"] is None
    assert record["cache_write_tokens"] is None
    assert record["reasoning_tokens"] is None
    assert record["total_tokens"] is None
    assert record["cost"] is None


def test_cache_token_fields_null_when_provider_omits_details():
    """Nemotron-style OpenAI usage: prompt/completion only, details=null."""
    usage = SimpleNamespace(
        prompt_tokens=22,
        completion_tokens=16,
        total_tokens=38,
        prompt_tokens_details=None,
        completion_tokens_details=None,
    )
    cu = normalize_usage(usage, provider="nvidia", api_mode="chat_completions")
    record = build_usage_telemetry_record(
        cu,
        provider="nvidia",
        model="nvidia/nemotron-3-super-120b-a12b",
        cost=None,
        cost_status="unknown",
    )
    assert record["input_tokens"] == 22
    assert record["output_tokens"] == 16
    assert record["cache_read_tokens"] is None
    assert record["cache_write_tokens"] is None
    assert record["reasoning_tokens"] is None
    assert record["cost"] is None
    # Aggregation ints remain 0 for DB summing — presence is the signal.
    assert cu.cache_read_tokens == 0


def test_reasoning_token_fields_from_completion_details():
    usage = SimpleNamespace(
        prompt_tokens=100,
        completion_tokens=500,
        completion_tokens_details=SimpleNamespace(reasoning_tokens=450),
    )
    cu = normalize_usage(usage, provider="deepseek", api_mode="chat_completions")
    assert cu.reasoning_tokens == 450
    assert "reasoning_tokens" in cu.reported_fields
    record = build_usage_telemetry_record(cu, provider="deepseek", model="deepseek-v4-flash")
    assert record["reasoning_tokens"] == 450


def test_streaming_usage_arriving_in_final_chunk_shape():
    """Final streamed chunk often looks like a normal usage object."""
    final_chunk_usage = {
        "prompt_tokens": 80,
        "completion_tokens": 12,
        "prompt_tokens_details": {"cached_tokens": 20},
    }
    cu = normalize_usage(final_chunk_usage, provider="openai", api_mode="chat_completions")
    assert cu.input_tokens == 60
    assert cu.cache_read_tokens == 20
    assert cu.usage_source == "provider_reported"


def test_provider_model_switch_mid_session_preserves_independent_routes():
    nemo = normalize_usage(
        SimpleNamespace(prompt_tokens=10, completion_tokens=2),
        provider="nvidia",
        api_mode="chat_completions",
    )
    opencode = normalize_usage(
        SimpleNamespace(
            input_tokens=1000,
            output_tokens=50,
            cache_read_input_tokens=2000,
            cache_creation_input_tokens=0,
        ),
        provider="opencode-go",
        api_mode="anthropic_messages",
    )
    r1 = build_usage_telemetry_record(
        nemo, provider="nvidia", model="nvidia/nemotron-3-super-120b-a12b", session_id="s1"
    )
    r2 = build_usage_telemetry_record(
        opencode, provider="opencode-go", model="minimax-m3", session_id="s1"
    )
    assert r1["provider"] == "nvidia"
    assert r2["provider"] == "opencode-go"
    assert r1["cache_read_tokens"] is None
    assert r2["cache_read_tokens"] == 2000
    assert r1["session_id"] == r2["session_id"] == "s1"


def test_unknown_model_pricing_yields_null_cost():
    cu = CanonicalUsage(
        input_tokens=1000,
        output_tokens=100,
        reported_fields=frozenset({"input_tokens", "output_tokens"}),
        usage_source="provider_reported",
        usage_confidence="high",
    )
    cost = estimate_usage_cost(
        "nvidia/nemotron-3-super-120b-a12b",
        cu,
        provider="nvidia",
        base_url="https://integrate.api.nvidia.com/v1",
    )
    assert cost.amount_usd is None
    assert cost.status == "unknown"
    record = build_usage_telemetry_record(
        cu,
        provider="nvidia",
        model="nvidia/nemotron-3-super-120b-a12b",
        cost=cost.amount_usd,
        cost_status=cost.status,
    )
    assert record["cost"] is None
    assert record["cost_status"] == "unknown"


def test_failed_and_retried_request_telemetry_fields():
    cu = CanonicalUsage(usage_source="unavailable", usage_confidence="none")
    record = build_usage_telemetry_record(
        cu,
        provider="nvidia",
        model="nvidia/nemotron-3-super-120b-a12b",
        retries=2,
        error="429 rate_limit_exceeded",
        rate_limited=True,
        task_succeeded=False,
    )
    assert record["retries"] == 2
    assert record["rate_limited"] is True
    assert record["error"] == "429 rate_limit_exceeded"
    assert record["task_succeeded"] is False
    assert record["input_tokens"] is None


def test_opencode_anthropic_wire_and_openai_compat_share_schema_keys():
    anthropic_shaped = normalize_usage(
        SimpleNamespace(
            input_tokens=100,
            output_tokens=20,
            cache_read_input_tokens=50,
            cache_creation_input_tokens=10,
        ),
        provider="opencode-go",
        api_mode="anthropic_messages",
    )
    openai_shaped = normalize_usage(
        SimpleNamespace(
            prompt_tokens=160,
            completion_tokens=20,
            prompt_tokens_details=SimpleNamespace(cached_tokens=50),
        ),
        provider="opencode-go",
        api_mode="chat_completions",
    )
    keys = set(build_usage_telemetry_record(anthropic_shaped, provider="opencode-go").keys())
    assert keys == set(
        build_usage_telemetry_record(openai_shaped, provider="opencode-go").keys()
    )
