"""Prompt-cache capability layer (transport/provider, not model-specific).

Hermes asks one question: what cache *mode* does this transport advertise?

Modes
-----
``NONE``     — do not emit Anthropic-style ``cache_control``; no automatic
               prefix cache assumed.
``AUTO``     — provider caches prefixes automatically; do **not** emit
               Anthropic ``cache_control`` (OpenAI / Gemini style).
``EXPLICIT`` — emit Anthropic-compatible ``cache_control`` breakpoints.

Layouts (only for ``EXPLICIT``)
-------------------------------
``native``   — markers on inner content blocks (Anthropic Messages wire).
``envelope`` — markers on OpenAI-wire content parts (OpenRouter / Qwen-on-Go).

Resolution order
----------------
1. Provider profile ``prompt_cache_capability(...)`` if implemented.
2. Transport/host registry fallback (custom endpoints, aggregators).

Never emit explicit markers unless the selected transport advertises
``EXPLICIT`` — unknown fields break strict OpenAI-compatible gateways.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional
from urllib.parse import urlparse


class PromptCacheMode(str, Enum):
    NONE = "none"
    AUTO = "auto"
    EXPLICIT = "explicit"


class PromptCacheLayout(str, Enum):
    NONE = "none"
    NATIVE = "native"
    ENVELOPE = "envelope"


@dataclass(frozen=True)
class PromptCacheCapability:
    """Declared prompt-cache behaviour for a provider/transport pair."""

    mode: PromptCacheMode
    layout: PromptCacheLayout = PromptCacheLayout.NONE
    supports_tools: bool = True
    supports_messages: bool = True
    source: str = ""  # which rule matched — for telemetry / insights

    @property
    def emit_explicit_markers(self) -> bool:
        return self.mode is PromptCacheMode.EXPLICIT

    @property
    def use_native_layout(self) -> bool:
        return (
            self.mode is PromptCacheMode.EXPLICIT
            and self.layout is PromptCacheLayout.NATIVE
        )

    def to_telemetry(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "layout": self.layout.value,
            "emit_markers": self.emit_explicit_markers,
            "supports_tools": self.supports_tools,
            "supports_messages": self.supports_messages,
            "source": self.source,
        }


def explicit_native(source: str) -> PromptCacheCapability:
    return PromptCacheCapability(
        mode=PromptCacheMode.EXPLICIT,
        layout=PromptCacheLayout.NATIVE,
        source=source,
    )


def explicit_envelope(source: str) -> PromptCacheCapability:
    return PromptCacheCapability(
        mode=PromptCacheMode.EXPLICIT,
        layout=PromptCacheLayout.ENVELOPE,
        source=source,
    )


def auto_cache(source: str) -> PromptCacheCapability:
    return PromptCacheCapability(
        mode=PromptCacheMode.AUTO,
        layout=PromptCacheLayout.NONE,
        source=source,
    )


def no_cache(source: str) -> PromptCacheCapability:
    return PromptCacheCapability(
        mode=PromptCacheMode.NONE,
        layout=PromptCacheLayout.NONE,
        source=source,
    )


def _hostname(base_url: str) -> str:
    try:
        return (urlparse(base_url or "").hostname or "").lower()
    except Exception:
        return ""


def _path(base_url: str) -> str:
    try:
        return (urlparse(base_url or "").path or "").lower()
    except Exception:
        return ""


def resolve_prompt_cache_capability(
    *,
    provider: str | None,
    base_url: str | None = None,
    api_mode: str | None = None,
    model: str | None = None,
) -> PromptCacheCapability:
    """Resolve cache capability for a provider + transport (+ optional model).

    Model is consulted only for *aggregator* routes where one OpenAI-wire
    endpoint fronts many upstream families with different cache contracts
    (OpenRouter Claude vs GPT, OpenCode Qwen vs GLM). Direct providers
    declare capability on their adapter / transport.
    """
    provider_l = (provider or "").strip().lower()
    base = base_url or ""
    mode = (api_mode or "").strip().lower()
    model_l = (model or "").strip().lower()
    host = _hostname(base)

    # ── 1) Provider adapter declaration ──────────────────────────
    try:
        from providers import get_provider_profile

        profile = get_provider_profile(provider_l) if provider_l else None
        if profile is not None:
            declared = profile.prompt_cache_capability(
                api_mode=mode or None,
                model=model,
                base_url=base or None,
            )
            if declared is not None:
                return declared
    except Exception:
        pass

    # ── 2) Transport / host registry fallback ────────────────────
    return _transport_registry_capability(
        provider=provider_l,
        base_url=base,
        api_mode=mode,
        model=model_l,
        host=host,
    )


def _transport_registry_capability(
    *,
    provider: str,
    base_url: str,
    api_mode: str,
    model: str,
    host: str,
) -> PromptCacheCapability:
    """Fallback when no provider profile declares a capability."""
    is_anthropic_wire = api_mode == "anthropic_messages"
    path = _path(base_url)

    # Native Anthropic host
    if is_anthropic_wire and (provider == "anthropic" or host == "api.anthropic.com"):
        return explicit_native("host:api.anthropic.com")

    # MiniMax Anthropic hosts (custom provider pointed at MiniMax)
    if is_anthropic_wire and host in {"api.minimax.io", "api.minimaxi.com"}:
        if path.rstrip("/").endswith("/anthropic") or "/anthropic" in path:
            return explicit_native(f"host:{host}/anthropic")

    # OpenCode Anthropic Messages surface (Go MiniMax etc.)
    if is_anthropic_wire and host.endswith("opencode.ai"):
        return explicit_native("host:opencode.ai+anthropic_messages")

    # Third-party Anthropic-compatible gateway serving Claude
    if is_anthropic_wire and "claude" in model:
        return explicit_native("transport:anthropic_messages+claude_model")

    # OpenRouter / Nous Portal — OpenAI wire, explicit envelope for
    # families that honour Anthropic-style markers.
    is_openrouter = host.endswith("openrouter.ai") or provider == "openrouter"
    is_nous = "nousresearch" in (base_url or "").lower() or provider == "nous"
    if is_openrouter or is_nous:
        return _aggregator_openai_wire_capability(
            model=model,
            source="openrouter" if is_openrouter else "nous",
        )

    # Default OpenAI-compatible: automatic caching if any — never emit markers
    if api_mode in {"", "chat_completions"}:
        return auto_cache("default:openai_wire_auto")

    return no_cache("default:unknown")


def aggregator_openai_wire_capability(
    *, model: str, source: str
) -> PromptCacheCapability:
    """OpenRouter/Nous: explicit envelope only for families that honour it.

    OpenRouter: Claude + Kimi (OpenRouter's Qwen routing has its own
    upstream caching; markers are not uniformly honouring).
    Nous Portal: Claude + Kimi + Qwen (Portal Qwen needs markers).
    """
    try:
        from agent.anthropic_adapter import _model_name_is_kimi_family

        is_kimi = _model_name_is_kimi_family(model) or "moonshot" in model
    except Exception:
        is_kimi = "kimi" in model or "moonshot" in model

    is_qwen = "qwen" in model
    include_qwen = source in {"nous", "nousresearch", "nous-portal"}
    if "claude" in model or is_kimi or (is_qwen and include_qwen):
        return explicit_envelope(f"aggregator:{source}+explicit_family")
    return auto_cache(f"aggregator:{source}+auto_family")


# Back-compat alias for internal callers.
_aggregator_openai_wire_capability = aggregator_openai_wire_capability


def capability_to_policy_tuple(
    cap: PromptCacheCapability,
) -> tuple[bool, bool]:
    """Map capability → legacy ``(should_cache, use_native_layout)`` tuple."""
    if not cap.emit_explicit_markers:
        return False, False
    return True, cap.use_native_layout


def capability_from_telemetry(raw: Any) -> Optional[PromptCacheCapability]:
    """Rehydrate a capability from session model_config.prompt_cache."""
    if not isinstance(raw, dict):
        return None
    try:
        mode = PromptCacheMode(str(raw.get("mode") or "none"))
        layout = PromptCacheLayout(str(raw.get("layout") or "none"))
    except ValueError:
        return None
    return PromptCacheCapability(
        mode=mode,
        layout=layout,
        supports_tools=bool(raw.get("supports_tools", True)),
        supports_messages=bool(raw.get("supports_messages", True)),
        source=str(raw.get("source") or ""),
    )


def summarize_capabilities(caps: list[PromptCacheCapability]) -> list[dict[str, Any]]:
    """Aggregate capabilities for insights display."""
    buckets: dict[tuple[str, str], int] = {}
    for c in caps:
        key = (c.mode.value, c.layout.value)
        buckets[key] = buckets.get(key, 0) + 1
    rows = []
    for (mode, layout), n in sorted(buckets.items(), key=lambda kv: -kv[1]):
        rows.append({"mode": mode, "layout": layout, "sessions": n})
    return rows


# Re-export for typing consumers
__all__ = [
    "PromptCacheMode",
    "PromptCacheLayout",
    "PromptCacheCapability",
    "resolve_prompt_cache_capability",
    "capability_to_policy_tuple",
    "capability_from_telemetry",
    "summarize_capabilities",
    "explicit_native",
    "explicit_envelope",
    "auto_cache",
    "no_cache",
    "aggregator_openai_wire_capability",
    "asdict",
]
