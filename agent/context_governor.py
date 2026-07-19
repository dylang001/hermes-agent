"""Adaptive live-context governor — continuity first, recover before fail.

Context Policy P0 (see ``docs/context-policy.md``):

* Budget the **live transcript** (messages + memory prefetch), never tool
  schemas alone (preserves the Telegram Hello recover-first fix).
* Default budgets are **percentages of the active model context window**,
  not fixed 20k/28k absolute caps.
* Four stages: normal → background optimisation → intelligent compaction →
  emergency recovery.
* Profiles (interactive / autonomous / batch) select stage ratios so a
  day-long coding chat is not constrained like a short-lived worker.

Runtime architecture remains frozen: this module only changes policy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

from agent.model_metadata import (
    estimate_messages_tokens_rough,
    estimate_request_tokens_rough,
    estimate_tokens_rough,
)

logger = logging.getLogger(__name__)

RecoveryAction = Literal["none", "compact", "fail"]
BudgetMode = Literal["adaptive", "absolute"]
ContextProfile = Literal["interactive", "autonomous", "batch", "auto"]
PolicyStage = Literal[
    "normal", "optimization", "compaction", "emergency", "disabled"
]

# Tool names whose results count toward the retrieval budget.
_RETRIEVAL_TOOLS = frozenset(
    {
        "read_file",
        "search_files",
        "session_search",
        "web_search",
        "web_extract",
        "skill_view",
        "skills_list",
        "browser_snapshot",
        "browser_navigate",
    }
)

_TOOL_SUMMARY_MAX_CHARS = 240

# Messaging / interactive surfaces — maximise continuity under profile=auto.
_INTERACTIVE_PLATFORMS = frozenset(
    {
        "cli",
        "tui",
        "desktop",
        "telegram",
        "discord",
        "slack",
        "whatsapp",
        "signal",
        "matrix",
        "mattermost",
        "email",
        "sms",
        "homeassistant",
        "bluebubbles",
        "feishu",
        "dingtalk",
        "wecom",
        "weixin",
        "qqbot",
        "yuanbao",
        "webhook",
        "api_server",
        "",  # unset → treat as interactive (local CLI default)
    }
)

_AUTONOMOUS_PLATFORMS = frozenset({"cron", "kanban", "curator"})

# Profile stage ratios — fractions of model context_length (live transcript).
_PROFILE_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "interactive": {
        "informational_ratio": 0.35,
        "optimization_ratio": 0.55,
        "compaction_ratio": 0.75,
        "emergency_ratio": 0.90,
        # Tool budgets as fractions of window (floored/ceiled at resolve).
        "max_tool_result_ratio": 0.08,
        "max_retrieval_ratio": 0.06,
        "max_memory_prefetch_ratio": 0.004,
        "compression_threshold": 0.70,
        "protect_last_n": 24,
    },
    "autonomous": {
        "informational_ratio": 0.25,
        "optimization_ratio": 0.40,
        "compaction_ratio": 0.60,
        "emergency_ratio": 0.85,
        "max_tool_result_ratio": 0.05,
        "max_retrieval_ratio": 0.04,
        "max_memory_prefetch_ratio": 0.003,
        "compression_threshold": 0.55,
        "protect_last_n": 12,
    },
    "batch": {
        "informational_ratio": 0.15,
        "optimization_ratio": 0.30,
        "compaction_ratio": 0.50,
        "emergency_ratio": 0.75,
        "max_tool_result_ratio": 0.04,
        "max_retrieval_ratio": 0.03,
        "max_memory_prefetch_ratio": 0.002,
        "compression_threshold": 0.45,
        "protect_last_n": 8,
    },
}

# Absolute-mode legacy defaults (budget_mode: absolute only).
_ABSOLUTE_DEFAULTS = {
    "max_live_tokens": 28_000,
    "target_tokens": 24_000,
    "soft_warning_tokens": 26_000,
    "auto_compact_tokens": 27_000,
    "max_retrieval_tokens": 5_000,
    "max_tool_result_tokens": 6_000,
    "max_memory_prefetch_tokens": 1_500,
}

# Floors/ceilings so tiny windows stay usable and huge windows don't
# allow multi-hundred-k tool dumps in one turn.
_TOOL_RESULT_FLOOR = 2_000
_TOOL_RESULT_CEILING = 80_000
_RETRIEVAL_FLOOR = 1_500
_RETRIEVAL_CEILING = 60_000
_PREFETCH_FLOOR = 400
_PREFETCH_CEILING = 8_000
_MIN_CONTEXT_FOR_ADAPTIVE = 8_000
# Below this, adaptive mode must NOT silently fall back to the legacy 28k
# absolute ceiling (that destroyed MiniMax continuity when context_length
# resolved to 0). Pass through instead and log loudly.
_MIN_SAFE_ADAPTIVE_WINDOW = 64_000


@dataclass
class ContextGovernorConfig:
    """Resolved budgets for a single provider request's live transcript."""

    enabled: bool = True
    budget_mode: BudgetMode = "adaptive"
    profile: str = "interactive"
    context_length: int = 0
    # Stage tokens (derived from ratios or absolute mode).
    informational_tokens: int = 0
    optimization_tokens: int = 0
    compaction_tokens: int = 0
    emergency_tokens: int = 0
    # Back-compat aliases used throughout call sites / tests.
    max_live_tokens: int = 28_000
    target_tokens: int = 24_000
    soft_warning_tokens: int = 26_000
    auto_compact_tokens: int = 27_000
    max_retrieval_tokens: int = 5_000
    max_tool_result_tokens: int = 6_000
    max_memory_prefetch_tokens: int = 1_500
    # Profile hints for the % compressor (applied at agent init).
    compression_threshold: Optional[float] = None
    protect_last_n: Optional[int] = None
    # Raw ratios retained for diagnostics / benchmarks.
    informational_ratio: float = 0.35
    optimization_ratio: float = 0.55
    compaction_ratio: float = 0.75
    emergency_ratio: float = 0.90
    resolved: bool = False

    @classmethod
    def from_config_dict(cls, raw: Optional[Dict[str, Any]]) -> "ContextGovernorConfig":
        """Build an unresolved config from yaml (call ``resolve`` next)."""
        raw = raw or {}
        if not isinstance(raw, dict):
            return cls()
        mode = str(raw.get("budget_mode") or "adaptive").strip().lower()
        if mode not in ("adaptive", "absolute"):
            mode = "adaptive"
        profile = str(raw.get("profile") or "auto").strip().lower() or "auto"
        return cls(
            enabled=bool(raw.get("enabled", True)),
            budget_mode=mode,  # type: ignore[arg-type]
            profile=profile,
            # Absolute knobs retained for absolute mode / test overrides.
            max_live_tokens=int(
                raw.get("max_live_tokens", _ABSOLUTE_DEFAULTS["max_live_tokens"])
                or _ABSOLUTE_DEFAULTS["max_live_tokens"]
            ),
            target_tokens=int(
                raw.get("target_tokens", _ABSOLUTE_DEFAULTS["target_tokens"])
                or _ABSOLUTE_DEFAULTS["target_tokens"]
            ),
            soft_warning_tokens=int(
                raw.get(
                    "soft_warning_tokens", _ABSOLUTE_DEFAULTS["soft_warning_tokens"]
                )
                or _ABSOLUTE_DEFAULTS["soft_warning_tokens"]
            ),
            auto_compact_tokens=int(
                raw.get(
                    "auto_compact_tokens", _ABSOLUTE_DEFAULTS["auto_compact_tokens"]
                )
                or _ABSOLUTE_DEFAULTS["auto_compact_tokens"]
            ),
            max_retrieval_tokens=int(
                raw.get(
                    "max_retrieval_tokens", _ABSOLUTE_DEFAULTS["max_retrieval_tokens"]
                )
                or _ABSOLUTE_DEFAULTS["max_retrieval_tokens"]
            ),
            max_tool_result_tokens=int(
                raw.get(
                    "max_tool_result_tokens",
                    _ABSOLUTE_DEFAULTS["max_tool_result_tokens"],
                )
                or _ABSOLUTE_DEFAULTS["max_tool_result_tokens"]
            ),
            max_memory_prefetch_tokens=int(
                raw.get(
                    "max_memory_prefetch_tokens",
                    _ABSOLUTE_DEFAULTS["max_memory_prefetch_tokens"],
                )
                or _ABSOLUTE_DEFAULTS["max_memory_prefetch_tokens"]
            ),
            informational_ratio=float(
                raw.get("informational_ratio")
                or _PROFILE_DEFAULTS["interactive"]["informational_ratio"]
            ),
            optimization_ratio=float(
                raw.get("optimization_ratio")
                or _PROFILE_DEFAULTS["interactive"]["optimization_ratio"]
            ),
            compaction_ratio=float(
                raw.get("compaction_ratio")
                or _PROFILE_DEFAULTS["interactive"]["compaction_ratio"]
            ),
            emergency_ratio=float(
                raw.get("emergency_ratio")
                or _PROFILE_DEFAULTS["interactive"]["emergency_ratio"]
            ),
            resolved=False,
        )

    @classmethod
    def load(cls) -> "ContextGovernorConfig":
        try:
            from hermes_cli.config import load_config

            cfg = load_config() or {}
            return cls.from_config_dict(cfg.get("context_governor"))
        except Exception:
            return cls()

    def resolve(
        self,
        *,
        context_length: int = 0,
        profile: Optional[str] = None,
        raw_config: Optional[Dict[str, Any]] = None,
    ) -> "ContextGovernorConfig":
        """Materialise stage token budgets from window + profile.

        Safe to call multiple times (e.g. model switch). Returns a new
        config instance; does not mutate ``self`` unless already a copy.
        """
        raw = raw_config if isinstance(raw_config, dict) else {}
        profiles_raw = raw.get("profiles") if isinstance(raw.get("profiles"), dict) else {}

        chosen = (profile or self.profile or "interactive").strip().lower()
        if chosen == "auto":
            chosen = "interactive"
        if chosen not in _PROFILE_DEFAULTS:
            chosen = "interactive"

        base_profile = dict(_PROFILE_DEFAULTS[chosen])
        user_profile = profiles_raw.get(chosen) if isinstance(profiles_raw.get(chosen), dict) else {}
        base_profile.update({k: v for k, v in user_profile.items() if v is not None})

        # Top-level ratio overrides beat profile defaults.
        for key in (
            "informational_ratio",
            "optimization_ratio",
            "compaction_ratio",
            "emergency_ratio",
            "max_tool_result_ratio",
            "max_retrieval_ratio",
            "max_memory_prefetch_ratio",
            "compression_threshold",
            "protect_last_n",
        ):
            if key in raw and raw[key] is not None:
                base_profile[key] = raw[key]

        info_r = float(base_profile["informational_ratio"])
        opt_r = float(base_profile["optimization_ratio"])
        comp_r = float(base_profile["compaction_ratio"])
        emerg_r = float(base_profile["emergency_ratio"])
        # Enforce monotonic stage order.
        opt_r = max(opt_r, info_r + 0.01)
        comp_r = max(comp_r, opt_r + 0.01)
        emerg_r = max(emerg_r, comp_r + 0.01)
        emerg_r = min(emerg_r, 0.98)

        cfg = replace(self)
        cfg.profile = chosen
        cfg.informational_ratio = info_r
        cfg.optimization_ratio = opt_r
        cfg.compaction_ratio = comp_r
        cfg.emergency_ratio = emerg_r
        cfg.compression_threshold = (
            float(base_profile["compression_threshold"])
            if base_profile.get("compression_threshold") is not None
            else None
        )
        cfg.protect_last_n = (
            int(base_profile["protect_last_n"])
            if base_profile.get("protect_last_n") is not None
            else None
        )

        window = int(context_length or 0)
        cfg.context_length = window

        # Adaptive without a known large window: refuse the silent 28k
        # absolute fallback. Stock compression.threshold handles pressure.
        if cfg.budget_mode == "adaptive" and window < _MIN_SAFE_ADAPTIVE_WINDOW:
            logger.warning(
                "Context governor: adaptive mode requires context_length≥%s "
                "(got %s) — disabling governor instead of falling back to "
                "absolute 28k live budget. Set model.context_length or fix "
                "provider context detection; or set budget_mode: absolute "
                "explicitly if you want the legacy ceiling.",
                f"{_MIN_SAFE_ADAPTIVE_WINDOW:,}",
                f"{window:,}",
            )
            cfg.enabled = False
            cfg.resolved = True
            return cfg

        if cfg.budget_mode == "absolute" or window < _MIN_CONTEXT_FOR_ADAPTIVE:
            # Absolute / tiny-window path — keep explicit token knobs.
            cfg.max_live_tokens = int(self.max_live_tokens)
            cfg.emergency_tokens = cfg.max_live_tokens
            cfg.auto_compact_tokens = int(self.auto_compact_tokens)
            cfg.compaction_tokens = cfg.auto_compact_tokens
            cfg.soft_warning_tokens = int(self.soft_warning_tokens)
            cfg.informational_tokens = cfg.soft_warning_tokens
            cfg.optimization_tokens = int(
                min(cfg.auto_compact_tokens, max(cfg.target_tokens, cfg.soft_warning_tokens))
            )
            cfg.target_tokens = int(self.target_tokens)
            cfg.max_retrieval_tokens = int(self.max_retrieval_tokens)
            cfg.max_tool_result_tokens = int(self.max_tool_result_tokens)
            cfg.max_memory_prefetch_tokens = int(self.max_memory_prefetch_tokens)
            cfg.resolved = True
            return cfg

        def _tok(ratio: float) -> int:
            return max(1_000, int(window * ratio))

        cfg.informational_tokens = _tok(info_r)
        cfg.optimization_tokens = _tok(opt_r)
        cfg.compaction_tokens = _tok(comp_r)
        cfg.emergency_tokens = _tok(emerg_r)

        # Aliases for existing call sites / metrics.
        cfg.soft_warning_tokens = cfg.informational_tokens
        cfg.target_tokens = cfg.optimization_tokens
        cfg.auto_compact_tokens = cfg.compaction_tokens
        cfg.max_live_tokens = cfg.emergency_tokens

        tool_r = float(base_profile.get("max_tool_result_ratio", 0.08))
        ret_r = float(base_profile.get("max_retrieval_ratio", 0.06))
        pref_r = float(base_profile.get("max_memory_prefetch_ratio", 0.004))
        cfg.max_tool_result_tokens = int(
            min(_TOOL_RESULT_CEILING, max(_TOOL_RESULT_FLOOR, window * tool_r))
        )
        cfg.max_retrieval_tokens = int(
            min(_RETRIEVAL_CEILING, max(_RETRIEVAL_FLOOR, window * ret_r))
        )
        cfg.max_memory_prefetch_tokens = int(
            min(_PREFETCH_CEILING, max(_PREFETCH_FLOOR, window * pref_r))
        )
        cfg.resolved = True
        return cfg


def resolve_context_profile(
    *,
    configured: str = "auto",
    platform: str = "",
    is_subagent: bool = False,
    is_cron: bool = False,
) -> str:
    """Map runtime role → interactive | autonomous | batch."""
    conf = (configured or "auto").strip().lower()
    if conf in ("interactive", "autonomous", "batch"):
        return conf
    if is_subagent:
        return "batch"
    plat = (platform or "").strip().lower()
    if is_cron or plat in _AUTONOMOUS_PLATFORMS:
        return "autonomous"
    if plat in _INTERACTIVE_PLATFORMS:
        return "interactive"
    # Unknown platform: prefer continuity (personal OS default).
    return "interactive"


def load_resolved_governor_config(
    *,
    context_length: int,
    platform: str = "",
    is_subagent: bool = False,
    is_cron: bool = False,
) -> ContextGovernorConfig:
    """Load yaml + resolve adaptive budgets for this agent."""
    raw: Dict[str, Any] = {}
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        raw = cfg.get("context_governor") or {}
        if not isinstance(raw, dict):
            raw = {}
    except Exception:
        raw = {}
    base = ContextGovernorConfig.from_config_dict(raw)
    profile = resolve_context_profile(
        configured=str(raw.get("profile") or base.profile or "auto"),
        platform=platform,
        is_subagent=is_subagent,
        is_cron=is_cron,
    )
    return base.resolve(
        context_length=context_length, profile=profile, raw_config=raw
    )


def _stage_for_live(live_tokens: int, cfg: ContextGovernorConfig) -> PolicyStage:
    """Stage name for logging / metrics (informational is soft-normal)."""
    if not cfg.enabled:
        return "disabled"
    if live_tokens >= cfg.max_live_tokens:
        return "emergency"
    if live_tokens >= cfg.auto_compact_tokens:
        return "compaction"
    if live_tokens >= cfg.optimization_tokens:
        return "optimization"
    if live_tokens >= cfg.soft_warning_tokens:
        return "normal"  # informational soft signal only
    return "normal"


@dataclass
class GovernorResult:
    messages: List[Dict[str, Any]]
    tools: Optional[List[Any]]
    memory_prefetch: str
    tokens_before: int
    tokens_after: int
    tokens_messages: int = 0
    tokens_tools: int = 0
    tokens_total: int = 0
    actions: List[str] = field(default_factory=list)
    recovery: RecoveryAction = "none"
    blocked: bool = False
    block_reason: str = ""
    stage: PolicyStage = "normal"
    config: ContextGovernorConfig = field(default_factory=ContextGovernorConfig)


def _msg_content(msg: Dict[str, Any]) -> str:
    content = msg.get("content")
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)


def _set_msg_content(msg: Dict[str, Any], text: str) -> None:
    content = msg.get("content")
    if isinstance(content, list):
        msg["content"] = [{"type": "text", "text": text}]
    else:
        msg["content"] = text


def _truncate_text(text: str, max_tokens: int, label: str) -> str:
    if max_tokens <= 0:
        return f"[{label} omitted — budget 0]"
    max_chars = max_tokens * 4
    if estimate_tokens_rough(text) <= max_tokens:
        return text
    keep = max(0, max_chars - 80)
    return text[:keep] + f"\n… [{label} truncated to ~{max_tokens} tokens]\n"


def _tool_name_for_result(
    messages: Sequence[Dict[str, Any]], tool_msg: Dict[str, Any]
) -> str:
    cid = tool_msg.get("tool_call_id") or ""
    if tool_msg.get("name"):
        return str(tool_msg["name"])
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            if tc.get("id") == cid:
                fn = tc.get("function") or {}
                return str(fn.get("name") or "")
    return ""


def _summarize_tool_content(tool_name: str, content: str) -> str:
    preview = content.strip().replace("\n", " ")
    if len(preview) > _TOOL_SUMMARY_MAX_CHARS:
        preview = preview[:_TOOL_SUMMARY_MAX_CHARS] + "…"
    return (
        f"[{tool_name or 'tool'} result summarized by context governor — "
        f"original ~{estimate_tokens_rough(content)} tokens. Preview: {preview}]"
    )


def cap_memory_prefetch(prefetch: str, max_tokens: int, actions: List[str]) -> str:
    if not prefetch:
        return ""
    before = estimate_tokens_rough(prefetch)
    if before <= max_tokens:
        return prefetch
    actions.append(f"memory_prefetch truncated {before}→{max_tokens} tok")
    return _truncate_text(prefetch, max_tokens, "memory-prefetch")


# Back-compat alias used by early call sites / tests.
_cap_memory_prefetch = cap_memory_prefetch


def _prune_tool_results(
    messages: List[Dict[str, Any]],
    *,
    max_tool_result_tokens: int,
    max_retrieval_tokens: int,
    actions: List[str],
) -> List[Dict[str, Any]]:
    """Cap aggregate tool-result and retrieval budgets, oldest first."""
    out = [dict(m) for m in messages]
    tool_idxs = [i for i, m in enumerate(out) if m.get("role") == "tool"]

    def _budget_ok() -> bool:
        tool_tok = 0
        retrieval_tok = 0
        for i in tool_idxs:
            content = _msg_content(out[i])
            tok = estimate_tokens_rough(content)
            tool_tok += tok
            name = _tool_name_for_result(out, out[i])
            if name in _RETRIEVAL_TOOLS:
                retrieval_tok += tok
        return (
            tool_tok <= max_tool_result_tokens
            and retrieval_tok <= max_retrieval_tokens
        )

    if _budget_ok():
        return out

    protect_newest = 1
    prune_order = (
        tool_idxs[:-protect_newest] if len(tool_idxs) > protect_newest else tool_idxs[:]
    )
    for i in prune_order:
        if _budget_ok():
            break
        content = _msg_content(out[i])
        if not content or content.startswith("["):
            continue
        name = _tool_name_for_result(out, out[i])
        _set_msg_content(out[i], _summarize_tool_content(name, content))
        actions.append(f"tool_result summarized ({name or 'tool'})")

    if not _budget_ok() and tool_idxs:
        i = tool_idxs[-1]
        content = _msg_content(out[i])
        name = _tool_name_for_result(out, out[i])
        remain = max(80, max_tool_result_tokens // 2)
        if name in _RETRIEVAL_TOOLS:
            remain = min(remain, max(80, max_retrieval_tokens // 2))
        _set_msg_content(
            out[i], _truncate_text(content, remain, f"{name or 'tool'}-result")
        )
        actions.append(f"tool_result truncated newest ({name or 'tool'})")

    return out


def _estimate_components(
    messages: Sequence[Dict[str, Any]],
    tools: Optional[Sequence[Any]],
    memory_prefetch: str,
) -> Tuple[int, int, int, int]:
    """Return (live_tokens, messages_tokens, tools_tokens, total_tokens)."""
    msgs = list(messages)
    messages_tokens = estimate_messages_tokens_rough(msgs) if msgs else 0
    prefetch_tokens = estimate_tokens_rough(memory_prefetch) if memory_prefetch else 0
    live_tokens = messages_tokens + prefetch_tokens
    tools_list = list(tools) if tools is not None else None
    tools_tokens = 0
    if tools_list:
        total_with_tools = estimate_request_tokens_rough(msgs, tools=tools_list)
        tools_tokens = max(0, total_with_tools - messages_tokens)
    total_tokens = live_tokens + tools_tokens
    return live_tokens, messages_tokens, tools_tokens, total_tokens


def _emergency_truncate_transcript(
    messages: List[Dict[str, Any]],
    *,
    max_live_tokens: int,
    actions: List[str],
) -> List[Dict[str, Any]]:
    """Last-resort: keep system + last user turn."""
    if not messages:
        return messages
    out = [dict(m) for m in messages]
    system = [m for m in out if m.get("role") == "system"]
    last_user_idx = None
    for i in range(len(out) - 1, -1, -1):
        if out[i].get("role") == "user":
            last_user_idx = i
            break
    kept: List[Dict[str, Any]] = []
    kept.extend(system[:1])
    if last_user_idx is not None:
        user_msg = dict(out[last_user_idx])
        content = _msg_content(user_msg)
        sys_tok = estimate_messages_tokens_rough(kept) if kept else 0
        user_budget = max(200, max_live_tokens - sys_tok - 50)
        if estimate_tokens_rough(content) > user_budget:
            _set_msg_content(
                user_msg, _truncate_text(content, user_budget, "user-message")
            )
            actions.append("emergency_truncated_user_message")
        kept.append(user_msg)
    elif out:
        kept.append(out[-1])
    actions.append("emergency_transcript_truncated")
    return kept


def govern_request(
    messages: Sequence[Dict[str, Any]],
    *,
    tools: Optional[Sequence[Any]] = None,
    memory_prefetch: str = "",
    config: Optional[ContextGovernorConfig] = None,
    after_recovery: bool = False,
    allow_emergency_truncate: bool = False,
) -> GovernorResult:
    """Enforce live-transcript budgets with staged, recover-first semantics.

    Stage 1 (normal): no tool-trace pruning, no compaction signal.
    Stage 2 (optimisation): prune/collapse low-value tool results only.
    Stage 3 (compaction): request intelligent auto-compact (caller).
    Stage 4 (emergency): compact / emergency truncate / fail after recovery.
    """
    cfg = config or ContextGovernorConfig()
    # Tests often construct absolute token knobs without resolve(); treat
    # unresolved configs with explicit max_live_tokens as absolute budgets.
    if not cfg.resolved and cfg.max_live_tokens > 0:
        if cfg.emergency_tokens <= 0:
            cfg = replace(
                cfg,
                emergency_tokens=cfg.max_live_tokens,
                compaction_tokens=cfg.auto_compact_tokens or cfg.max_live_tokens,
                optimization_tokens=cfg.target_tokens or cfg.soft_warning_tokens,
                informational_tokens=cfg.soft_warning_tokens,
                resolved=True,
            )

    tools_list = list(tools) if tools is not None else None
    msgs = [dict(m) for m in messages]
    prefetch = memory_prefetch or ""
    actions: List[str] = []

    live_before, _, tools_tok_before, total_before = _estimate_components(
        msgs, tools_list, prefetch
    )
    tokens_before = live_before

    if not cfg.enabled:
        return GovernorResult(
            messages=msgs,
            tools=tools_list,
            memory_prefetch=prefetch,
            tokens_before=tokens_before,
            tokens_after=tokens_before,
            tokens_messages=live_before,
            tokens_tools=tools_tok_before,
            tokens_total=total_before,
            actions=[],
            recovery="none",
            blocked=False,
            stage="disabled",
            config=cfg,
        )

    # Prefetch always capped (cheap, never user-visible conversation loss).
    prefetch = cap_memory_prefetch(
        prefetch, cfg.max_memory_prefetch_tokens, actions
    )

    live_probe, _, _, _ = _estimate_components(msgs, tools_list, prefetch)
    stage = _stage_for_live(live_probe, cfg)

    # Stage 1 — Normal: leave the conversation alone.
    # Stage 2+ — Background optimisation: prune tool traces only.
    if live_probe >= cfg.optimization_tokens:
        msgs = _prune_tool_results(
            msgs,
            max_tool_result_tokens=cfg.max_tool_result_tokens,
            max_retrieval_tokens=cfg.max_retrieval_tokens,
            actions=actions,
        )
        if actions:
            actions.append("stage_optimization_prune")

    live_after, msg_tok, tools_tok, total_after = _estimate_components(
        msgs, tools_list, prefetch
    )
    stage = _stage_for_live(live_after, cfg)

    # Approaching compaction: force-summarize older tool results (still not
    # summarising user/assistant dialogue — that is the compressor's job).
    if live_after >= cfg.auto_compact_tokens:
        tool_idxs = [i for i, m in enumerate(msgs) if m.get("role") == "tool"]
        for i in tool_idxs[:-1]:
            content = _msg_content(msgs[i])
            if content and "summarized by context governor" not in content:
                name = _tool_name_for_result(msgs, msgs[i])
                _set_msg_content(msgs[i], _summarize_tool_content(name, content))
                actions.append(f"tool_result force-summarized ({name or 'tool'})")
        live_after, msg_tok, tools_tok, total_after = _estimate_components(
            msgs, tools_list, prefetch
        )
        stage = _stage_for_live(live_after, cfg)

    if tools_tok and total_after > cfg.max_live_tokens and live_after <= cfg.max_live_tokens:
        actions.append(
            f"tools_overhead_outside_live_budget tools≈{tools_tok:,} "
            f"live≈{live_after:,} total≈{total_after:,}"
        )
        logger.info(
            "Context governor: tool schemas ≈%s tokens sit outside the live "
            "transcript budget (live≈%s / emergency=%s profile=%s); allowing",
            f"{tools_tok:,}",
            f"{live_after:,}",
            f"{cfg.max_live_tokens:,}",
            cfg.profile,
        )

    recovery: RecoveryAction = "none"
    blocked = False
    block_reason = ""

    if live_after > cfg.soft_warning_tokens and live_after < cfg.optimization_tokens:
        actions.append(
            f"informational live≈{live_after:,} "
            f"({cfg.informational_ratio:.0%} of window)"
            if cfg.context_length
            else f"informational live≈{live_after:,}"
        )

    if live_after > cfg.max_live_tokens:
        stage = "emergency"
        if not after_recovery:
            recovery = "compact"
            actions.append("recovery_compact_needed")
            logger.info(
                "Context governor [%s/%s]: live≈%s > emergency %s — requesting "
                "compaction (tools≈%s excluded from live budget)",
                cfg.profile,
                cfg.budget_mode,
                f"{live_after:,}",
                f"{cfg.max_live_tokens:,}",
                f"{tools_tok:,}",
            )
        else:
            if allow_emergency_truncate:
                msgs = _emergency_truncate_transcript(
                    msgs, max_live_tokens=cfg.max_live_tokens, actions=actions
                )
                live_after, msg_tok, tools_tok, total_after = _estimate_components(
                    msgs, tools_list, prefetch
                )
            if live_after > cfg.max_live_tokens:
                recovery = "fail"
                blocked = True
                block_reason = (
                    f"Live transcript ~{live_after:,} tokens still exceeds "
                    f"governor emergency budget of {cfg.max_live_tokens:,} "
                    f"(profile={cfg.profile}, window={cfg.context_length or 'n/a'}) "
                    f"after automatic recovery. Start a fresh session with /new, "
                    f"or continue in a new working context."
                )
                actions.append("blocked_after_recovery")
                logger.warning(block_reason)
            else:
                actions.append("emergency_truncate_recovered")
                recovery = "none"
                stage = _stage_for_live(live_after, cfg)
    elif live_after >= cfg.auto_compact_tokens and not after_recovery:
        stage = "compaction"
        recovery = "compact"
        actions.append("soft_auto_compact")
        logger.info(
            "Context governor [%s]: live≈%s crossed compaction=%s — "
            "requesting intelligent compaction",
            cfg.profile,
            f"{live_after:,}",
            f"{cfg.auto_compact_tokens:,}",
        )
    elif live_after >= cfg.optimization_tokens:
        stage = "optimization"
        if not any("stage_optimization" in a for a in actions):
            actions.append(f"stage_optimization live≈{live_after:,}")
    elif live_after >= cfg.soft_warning_tokens:
        actions.append(f"soft_warning live≈{live_after:,}")

    return GovernorResult(
        messages=msgs,
        tools=tools_list,
        memory_prefetch=prefetch,
        tokens_before=tokens_before,
        tokens_after=live_after,
        tokens_messages=msg_tok,
        tokens_tools=tools_tok,
        tokens_total=total_after,
        actions=actions,
        recovery=recovery,
        blocked=blocked,
        block_reason=block_reason,
        stage=stage,
        config=cfg,
    )
