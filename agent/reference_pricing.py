"""Versioned provider/model reference pricing registry.

Separates **actual billed cost** (what the connected provider charged) from
**reference token cost** (what the same usage would cost at a documented public
or subscription-equivalent rate).

Rules
-----
- Never write a reference estimate into ``actual_cost_usd``.
- Historical estimates are recomputed from token counters + the registry; do not
  permanently bake today's rates into old usage rows.
- Missing optional rates (e.g. cache) yield a partial total with reduced
  confidence rather than inventing a number.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal, Optional, Sequence

from agent.usage_pricing import CanonicalUsage

_ZERO = Decimal("0")
_ONE_MILLION = Decimal("1000000")
_CENT = Decimal("0.01")

PricingType = Literal[
    "provider_billed",
    "subscription_reference",
    "public_reference",
    "free_prototype",
    "self_hosted",
    "unknown",
]
CostConfidence = Literal["high", "medium", "low", "none"]


def _d(value: str | float | int | None) -> Optional[Decimal]:
    if value is None:
        return None
    return Decimal(str(value))


def _utc(dt: datetime | None = None) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class ReferencePricingEntry:
    """One versioned rate card for a billing provider / model / route."""

    billing_provider: str
    model_id: str
    pricing_route: str
    currency: str
    input_per_million: Optional[Decimal]
    cache_read_per_million: Optional[Decimal]
    cache_write_per_million: Optional[Decimal]
    output_per_million: Optional[Decimal]
    reasoning_per_million: Optional[Decimal]
    effective_from: datetime
    effective_to: Optional[datetime]
    source_url: str
    pricing_type: PricingType
    aliases: tuple[str, ...] = ()

    def covers_model(self, model_id: str) -> bool:
        needle = (model_id or "").strip().lower()
        if not needle:
            return False
        if needle == self.model_id.lower():
            return True
        bare = needle.rsplit("/", 1)[-1]
        if bare == self.model_id.lower().rsplit("/", 1)[-1]:
            return True
        return any(needle == a.lower() or bare == a.lower().rsplit("/", 1)[-1] for a in self.aliases)

    def active_at(self, when: datetime) -> bool:
        ts = _utc(when)
        start = _utc(self.effective_from)
        if ts < start:
            return False
        if self.effective_to is None:
            return True
        return ts < _utc(self.effective_to)


@dataclass(frozen=True)
class ReferenceCostResult:
    """Shadow-mode reference cost — never a substitute for actual billing."""

    reference_cost_usd: Optional[Decimal]
    reference_cost_basis: str
    pricing_source: str
    pricing_effective_date: str
    pricing_type: PricingType
    cost_confidence: CostConfidence
    input_usd: Optional[Decimal] = None
    cache_read_usd: Optional[Decimal] = None
    cache_write_usd: Optional[Decimal] = None
    output_usd: Optional[Decimal] = None
    reasoning_usd: Optional[Decimal] = None
    notes: tuple[str, ...] = ()
    entry: Optional[ReferencePricingEntry] = None

    def to_dict(self) -> dict[str, Any]:
        def _f(value: Optional[Decimal]) -> Optional[float]:
            if value is None:
                return None
            return float(value)

        return {
            "reference_cost_usd": _f(self.reference_cost_usd),
            "reference_cost_basis": self.reference_cost_basis,
            "pricing_source": self.pricing_source,
            "pricing_effective_date": self.pricing_effective_date,
            "pricing_type": self.pricing_type,
            "cost_confidence": self.cost_confidence,
            "cost_breakdown": {
                "input_usd": _f(self.input_usd),
                "cache_read_usd": _f(self.cache_read_usd),
                "cache_write_usd": _f(self.cache_write_usd),
                "output_usd": _f(self.output_usd),
                "reasoning_usd": _f(self.reasoning_usd),
            },
            "notes": list(self.notes),
        }


# Versioned registry. Append new rows when rates change; leave old rows with
# effective_to set so historical recomputation stays correct.
_REFERENCE_PRICING_REGISTRY: tuple[ReferencePricingEntry, ...] = (
    ReferencePricingEntry(
        billing_provider="opencode-go",
        model_id="minimax-m3",
        pricing_route="opencode.ai/zen/go",
        currency="USD",
        input_per_million=_d("0.30"),
        cache_read_per_million=_d("0.06"),
        cache_write_per_million=None,
        output_per_million=_d("1.20"),
        reasoning_per_million=None,
        effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        effective_to=None,
        source_url="https://opencode.ai/docs",
        pricing_type="subscription_reference",
        aliases=("minimax/minimax-m3",),
    ),
    # Public market reference for benchmarking (OpenRouter published list price).
    # Distinct from whatever NVIDIA NIM trial endpoint bills as actual ($0 today).
    ReferencePricingEntry(
        billing_provider="nvidia",
        model_id="nvidia/nemotron-3-super-120b-a12b",
        pricing_route="integrate.api.nvidia.com",
        currency="USD",
        input_per_million=_d("0.08"),
        cache_read_per_million=None,
        cache_write_per_million=None,
        output_per_million=_d("0.45"),
        reasoning_per_million=None,
        effective_from=datetime(2026, 3, 11, tzinfo=timezone.utc),
        effective_to=None,
        source_url="https://openrouter.ai/nvidia/nemotron-3-super-120b-a12b",
        pricing_type="public_reference",
        aliases=(
            "nemotron-3-super-120b-a12b",
            "nvidia/nemotron-3-super",
            "nemotron-3-super",
        ),
    ),
)


def list_reference_pricing_entries() -> tuple[ReferencePricingEntry, ...]:
    return _REFERENCE_PRICING_REGISTRY


def _normalize_provider(provider: str | None) -> str:
    return (provider or "").strip().lower()


def _normalize_route(pricing_route: str | None, base_url: str | None = None) -> str:
    route = (pricing_route or "").strip().lower()
    if route:
        return route
    base = (base_url or "").strip().lower()
    if "opencode.ai" in base:
        return "opencode.ai/zen/go"
    if "integrate.api.nvidia.com" in base or "api.nvidia.com" in base:
        return "integrate.api.nvidia.com"
    return ""


def lookup_reference_pricing(
    *,
    billing_provider: str | None,
    model_id: str | None,
    pricing_route: str | None = None,
    base_url: str | None = None,
    at: datetime | None = None,
) -> Optional[ReferencePricingEntry]:
    """Return the active registry entry for provider/model/route at ``at``."""
    provider = _normalize_provider(billing_provider)
    model = (model_id or "").strip()
    route = _normalize_route(pricing_route, base_url)
    when = _utc(at)

    candidates: list[ReferencePricingEntry] = []
    for entry in _REFERENCE_PRICING_REGISTRY:
        if _normalize_provider(entry.billing_provider) != provider:
            continue
        if not entry.covers_model(model):
            continue
        if not entry.active_at(when):
            continue
        if route and entry.pricing_route and route not in entry.pricing_route and entry.pricing_route not in route:
            # Prefer exact route match; keep as fallback if nothing better matches.
            candidates.append(entry)
            continue
        return entry

    if candidates:
        # Route mismatched but provider+model matched — still usable as reference.
        return candidates[0]
    return None


def _bucket_cost(tokens: int, rate: Optional[Decimal]) -> tuple[Optional[Decimal], Optional[str]]:
    if tokens <= 0:
        return _ZERO if rate is not None else _ZERO, None
    if rate is None:
        return None, "missing_rate"
    return (Decimal(tokens) * rate / _ONE_MILLION), None


def compute_reference_cost(
    usage: CanonicalUsage,
    entry: ReferencePricingEntry,
) -> ReferenceCostResult:
    """Compute reference USD for token usage against a registry entry."""
    notes: list[str] = []
    if entry.pricing_type == "subscription_reference":
        notes.append(
            "Subscription-equivalent token benchmark; not the user's subscription invoice."
        )
    if entry.pricing_type == "public_reference":
        notes.append("Public market reference rate for cross-model benchmarking.")
    if entry.pricing_type == "free_prototype":
        notes.append("Free prototype route — reference rates may be unavailable.")

    input_usd, input_miss = _bucket_cost(usage.input_tokens, entry.input_per_million)
    cache_read_usd, cache_read_miss = _bucket_cost(
        usage.cache_read_tokens, entry.cache_read_per_million
    )
    cache_write_usd, cache_write_miss = _bucket_cost(
        usage.cache_write_tokens, entry.cache_write_per_million
    )
    output_usd, output_miss = _bucket_cost(usage.output_tokens, entry.output_per_million)
    reasoning_usd, reasoning_miss = _bucket_cost(
        usage.reasoning_tokens, entry.reasoning_per_million
    )

    missing: list[str] = []
    if usage.input_tokens and input_miss:
        missing.append("input")
    if usage.cache_read_tokens and cache_read_miss:
        missing.append("cache_read")
        notes.append("cache_read_per_million unavailable — excluded from reference total")
    if usage.cache_write_tokens and cache_write_miss:
        missing.append("cache_write")
        notes.append("cache_write_per_million unavailable — excluded from reference total")
    if usage.output_tokens and output_miss:
        missing.append("output")
    if usage.reasoning_tokens and reasoning_miss:
        # Reasoning often folds into output; omit quietly unless rate exists.
        missing.append("reasoning")

    # Required buckets for a usable total: input+output rates when those tokens exist.
    if (usage.input_tokens and input_usd is None) or (usage.output_tokens and output_usd is None):
        return ReferenceCostResult(
            reference_cost_usd=None,
            reference_cost_basis="unavailable",
            pricing_source=entry.source_url,
            pricing_effective_date=_utc(entry.effective_from).date().isoformat(),
            pricing_type=entry.pricing_type,
            cost_confidence="none",
            notes=tuple(notes + ["required token rates missing"]),
            entry=entry,
        )

    if (
        entry.input_per_million is None
        and entry.output_per_million is None
        and entry.cache_read_per_million is None
    ):
        return ReferenceCostResult(
            reference_cost_usd=None,
            reference_cost_basis="unavailable",
            pricing_source=entry.source_url,
            pricing_effective_date=_utc(entry.effective_from).date().isoformat(),
            pricing_type=entry.pricing_type,
            cost_confidence="none",
            notes=tuple(notes + ["no token rates on registry entry"]),
            entry=entry,
        )

    total = _ZERO
    for part in (input_usd, cache_read_usd, cache_write_usd, output_usd, reasoning_usd):
        if part is not None:
            total += part

    if missing and {"input", "output"} & set(missing):
        confidence: CostConfidence = "none"
    elif missing:
        confidence = "medium"
    else:
        confidence = "high"

    return ReferenceCostResult(
        reference_cost_usd=total,
        reference_cost_basis="token_rates",
        pricing_source=entry.source_url,
        pricing_effective_date=_utc(entry.effective_from).date().isoformat(),
        pricing_type=entry.pricing_type,
        cost_confidence=confidence,
        input_usd=input_usd,
        cache_read_usd=cache_read_usd if usage.cache_read_tokens or entry.cache_read_per_million is not None else None,
        cache_write_usd=cache_write_usd if usage.cache_write_tokens else None,
        output_usd=output_usd,
        reasoning_usd=reasoning_usd if usage.reasoning_tokens else None,
        notes=tuple(notes),
        entry=entry,
    )


def compute_reference_cost_for_route(
    *,
    billing_provider: str | None,
    model_id: str | None,
    usage: CanonicalUsage,
    pricing_route: str | None = None,
    base_url: str | None = None,
    at: datetime | None = None,
) -> ReferenceCostResult:
    entry = lookup_reference_pricing(
        billing_provider=billing_provider,
        model_id=model_id,
        pricing_route=pricing_route,
        base_url=base_url,
        at=at,
    )
    if entry is None:
        return ReferenceCostResult(
            reference_cost_usd=None,
            reference_cost_basis="unavailable",
            pricing_source="",
            pricing_effective_date="",
            pricing_type="unknown",
            cost_confidence="none",
            notes=("no reference pricing registry entry",),
        )
    return compute_reference_cost(usage, entry)


def attach_reference_cost_fields(
    telemetry: dict[str, Any],
    usage: CanonicalUsage,
    *,
    provider: str | None,
    model: str | None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Add reference cost fields to a telemetry dict without touching actual cost."""
    result = compute_reference_cost_for_route(
        billing_provider=provider,
        model_id=model,
        usage=usage,
        base_url=base_url,
    )
    out = dict(telemetry)
    # Explicitly preserve any existing actual/estimated cost keys.
    out["reference_cost_usd"] = (
        float(result.reference_cost_usd) if result.reference_cost_usd is not None else None
    )
    out["reference_cost_basis"] = result.reference_cost_basis
    out["pricing_source"] = result.pricing_source
    out["pricing_effective_date"] = result.pricing_effective_date
    out["pricing_type"] = result.pricing_type
    out["cost_confidence"] = result.cost_confidence
    out["reference_cost_breakdown"] = result.to_dict()["cost_breakdown"]
    return out


def reference_cost_from_counters(
    *,
    billing_provider: str | None,
    model_id: str | None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    reasoning_tokens: int = 0,
    pricing_route: str | None = None,
    base_url: str | None = None,
    at: datetime | None = None,
) -> ReferenceCostResult:
    usage = CanonicalUsage(
        input_tokens=int(input_tokens or 0),
        output_tokens=int(output_tokens or 0),
        cache_read_tokens=int(cache_read_tokens or 0),
        cache_write_tokens=int(cache_write_tokens or 0),
        reasoning_tokens=int(reasoning_tokens or 0),
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
    return compute_reference_cost_for_route(
        billing_provider=billing_provider,
        model_id=model_id,
        usage=usage,
        pricing_route=pricing_route,
        base_url=base_url,
        at=at,
    )


def summarize_reference_coverage(
    rows: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Compute unknown-price coverage across analytics rows."""
    total = 0
    priced = 0
    unknown = 0
    reference_total = _ZERO
    for row in rows:
        total += 1
        ref = row.get("reference_cost_usd")
        if ref is None:
            unknown += 1
        else:
            priced += 1
            reference_total += Decimal(str(ref))
    pct_unknown = (unknown / total * 100.0) if total else 0.0
    return {
        "rows": total,
        "priced_rows": priced,
        "unknown_rows": unknown,
        "unknown_price_coverage_pct": round(pct_unknown, 2),
        "total_reference_cost_usd": float(reference_total),
    }


def round_usd(value: Decimal, places: int = 2) -> Decimal:
    quant = Decimal("1").scaleb(-places)
    return value.quantize(quant, rounding=ROUND_HALF_UP)
