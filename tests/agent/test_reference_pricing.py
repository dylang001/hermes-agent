"""Tests for the versioned reference pricing registry (shadow mode)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from agent.reference_pricing import (
    ReferencePricingEntry,
    attach_reference_cost_fields,
    compute_reference_cost,
    compute_reference_cost_for_route,
    lookup_reference_pricing,
    reference_cost_from_counters,
    round_usd,
    summarize_reference_coverage,
)
from agent.usage_pricing import CanonicalUsage, build_usage_telemetry_record


def _usage(**kwargs) -> CanonicalUsage:
    defaults = dict(
        input_tokens=0,
        output_tokens=0,
        cache_read_tokens=0,
        cache_write_tokens=0,
        reasoning_tokens=0,
        reported_fields=frozenset(
            {
                "input_tokens",
                "output_tokens",
                "cache_read_tokens",
                "cache_write_tokens",
                "reasoning_tokens",
            }
        ),
        usage_source="provider_reported",
        usage_confidence="high",
    )
    defaults.update(kwargs)
    return CanonicalUsage(**defaults)


def test_opencode_minimax_subscription_reference_rates():
    entry = lookup_reference_pricing(
        billing_provider="opencode-go",
        model_id="minimax-m3",
        base_url="https://opencode.ai/zen/go",
    )
    assert entry is not None
    assert entry.pricing_type == "subscription_reference"
    assert entry.input_per_million == Decimal("0.30")
    assert entry.cache_read_per_million == Decimal("0.06")
    assert entry.cache_write_per_million is None
    assert entry.output_per_million == Decimal("1.20")


def test_minimax_historical_benchmark_totals():
    """Fresh 4.6M + cache 67.5M + out 348k ≈ $5.85 at published OpenCode rates."""
    result = reference_cost_from_counters(
        billing_provider="opencode-go",
        model_id="minimax-m3",
        input_tokens=4_611_389,
        cache_read_tokens=67_521_666,
        output_tokens=348_033,
        base_url="https://opencode.ai/zen/go",
    )
    assert result.reference_cost_usd is not None
    assert result.cost_confidence == "high"
    assert result.pricing_type == "subscription_reference"
    assert round_usd(result.input_usd) == Decimal("1.38")
    assert round_usd(result.cache_read_usd) == Decimal("4.05")
    assert round_usd(result.output_usd) == Decimal("0.42")
    assert round_usd(result.reference_cost_usd) == Decimal("5.85")
    assert "subscription" in " ".join(result.notes).lower() or "Subscription" in "".join(
        result.notes
    )


def test_nvidia_public_reference_benchmark_rates():
    """User asked to benchmark with published market rates (not free/null)."""
    entry = lookup_reference_pricing(
        billing_provider="nvidia",
        model_id="nvidia/nemotron-3-super-120b-a12b",
        base_url="https://integrate.api.nvidia.com/v1",
    )
    assert entry is not None
    assert entry.pricing_type == "public_reference"
    assert entry.input_per_million == Decimal("0.08")
    assert entry.output_per_million == Decimal("0.45")
    assert entry.cache_read_per_million is None


def test_nvidia_historical_reference_cost():
    result = reference_cost_from_counters(
        billing_provider="nvidia",
        model_id="nvidia/nemotron-3-super-120b-a12b",
        input_tokens=3_370_653,
        output_tokens=27_643,
        base_url="https://integrate.api.nvidia.com/v1",
    )
    assert result.reference_cost_usd is not None
    # 3,370,653 * 0.08 / 1e6 + 27,643 * 0.45 / 1e6 ≈ 0.282
    assert round_usd(result.reference_cost_usd, 3) == Decimal("0.282")
    assert result.cost_confidence == "high"


def test_missing_cache_price_partial_total_medium_confidence():
    entry = ReferencePricingEntry(
        billing_provider="nvidia",
        model_id="nvidia/nemotron-3-super-120b-a12b",
        pricing_route="integrate.api.nvidia.com",
        currency="USD",
        input_per_million=Decimal("0.08"),
        cache_read_per_million=None,
        cache_write_per_million=None,
        output_per_million=Decimal("0.45"),
        reasoning_per_million=None,
        effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        effective_to=None,
        source_url="https://example.test/pricing",
        pricing_type="public_reference",
    )
    usage = _usage(input_tokens=1_000_000, output_tokens=1_000_000, cache_read_tokens=500_000)
    result = compute_reference_cost(usage, entry)
    assert result.reference_cost_usd == Decimal("0.08") + Decimal("0.45")
    assert result.cache_read_usd is None
    assert result.cost_confidence == "medium"
    assert any("cache_read" in n for n in result.notes)


def test_unknown_pricing_returns_none():
    result = compute_reference_cost_for_route(
        billing_provider="unknown-provider",
        model_id="mystery-model",
        usage=_usage(input_tokens=100, output_tokens=50),
    )
    assert result.reference_cost_usd is None
    assert result.pricing_type == "unknown"
    assert result.cost_confidence == "none"


def test_model_alias_lookup():
    entry = lookup_reference_pricing(
        billing_provider="nvidia",
        model_id="nemotron-3-super-120b-a12b",
        pricing_route="integrate.api.nvidia.com",
    )
    assert entry is not None
    assert "nemotron" in entry.model_id


def test_pricing_version_change_effective_window():
    """Old rates apply before effective_to; new rates after effective_from."""
    # Simulate by looking up current registry at a date before nvidia release.
    before = lookup_reference_pricing(
        billing_provider="nvidia",
        model_id="nvidia/nemotron-3-super-120b-a12b",
        at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    after = lookup_reference_pricing(
        billing_provider="nvidia",
        model_id="nvidia/nemotron-3-super-120b-a12b",
        at=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    assert before is None
    assert after is not None


def test_never_writes_reference_into_actual_or_cost_fields():
    usage = _usage(input_tokens=1000, output_tokens=100)
    telemetry = build_usage_telemetry_record(
        usage,
        provider="opencode-go",
        model="minimax-m3",
        cost=None,
        cost_status="unknown",
    )
    enriched = attach_reference_cost_fields(
        telemetry,
        usage,
        provider="opencode-go",
        model="minimax-m3",
        base_url="https://opencode.ai/zen/go",
    )
    assert enriched["cost"] is None
    assert enriched.get("actual_cost_usd") is None
    assert enriched["reference_cost_usd"] is not None
    assert enriched["cost_status"] == "unknown"


def test_free_prototype_entry_with_null_rates():
    entry = ReferencePricingEntry(
        billing_provider="nvidia",
        model_id="nvidia/free-proto",
        pricing_route="integrate.api.nvidia.com",
        currency="USD",
        input_per_million=None,
        cache_read_per_million=None,
        cache_write_per_million=None,
        output_per_million=None,
        reasoning_per_million=None,
        effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        effective_to=None,
        source_url="https://example.test/free",
        pricing_type="free_prototype",
    )
    result = compute_reference_cost(_usage(input_tokens=100, output_tokens=10), entry)
    assert result.reference_cost_usd is None
    assert result.pricing_type == "free_prototype"
    assert result.cost_confidence == "none"


def test_subscription_notes_separate_from_invoice():
    result = reference_cost_from_counters(
        billing_provider="opencode-go",
        model_id="minimax-m3",
        input_tokens=1_000_000,
        output_tokens=0,
    )
    assert result.pricing_type == "subscription_reference"
    assert any("invoice" in n.lower() or "subscription" in n.lower() for n in result.notes)


def test_coverage_summary():
    summary = summarize_reference_coverage(
        [
            {"reference_cost_usd": 1.2},
            {"reference_cost_usd": None},
            {"reference_cost_usd": 0.5},
        ]
    )
    assert summary["rows"] == 3
    assert summary["priced_rows"] == 2
    assert summary["unknown_rows"] == 1
    assert summary["unknown_price_coverage_pct"] == 33.33
    assert summary["total_reference_cost_usd"] == 1.7
