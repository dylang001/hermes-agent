"""Live-context governor — recover first, hard-block last.

Phase 1 introduced an absolute live-token budget. The first cut treated the
governor as a gatekeeper and counted tool schemas toward the same budget as
the transcript. That created an unreachable UX:

* Governor: "28,015 > 28,000 — blocked"
* /compress: "4 messages, ~1,476 tokens — nothing to compress"

Tool schemas are not compressible by /compress. This module now:

1. Budgets the **live transcript** (messages + memory prefetch), not tool schemas
2. Prunes/summarizes tool results under pressure
3. Signals **recovery** (auto-compact) instead of blocking ordinary turns
4. Hard-blocks only after emergency truncation still cannot fit the transcript

Tool/system overhead is reported for diagnostics but never alone causes a
user-visible hard stop.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Sequence

from agent.model_metadata import (
    estimate_messages_tokens_rough,
    estimate_request_tokens_rough,
    estimate_tokens_rough,
)

logger = logging.getLogger(__name__)

RecoveryAction = Literal["none", "compact", "fail"]

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


@dataclass
class ContextGovernorConfig:
    """Budgets for a single provider request's live transcript."""

    enabled: bool = True
    # Compressible live payload budget (messages + prefetch). NOT tool schemas.
    max_live_tokens: int = 28_000
    # Soft tiers — orchestrate recovery before the hard ceiling.
    target_tokens: int = 24_000
    soft_warning_tokens: int = 26_000
    auto_compact_tokens: int = 27_000
    max_retrieval_tokens: int = 5_000
    max_tool_result_tokens: int = 6_000
    max_memory_prefetch_tokens: int = 1_500

    @classmethod
    def from_config_dict(cls, raw: Optional[Dict[str, Any]]) -> "ContextGovernorConfig":
        raw = raw or {}
        if not isinstance(raw, dict):
            return cls()
        max_live = int(raw.get("max_live_tokens", 28_000) or 28_000)
        return cls(
            enabled=bool(raw.get("enabled", True)),
            max_live_tokens=max_live,
            target_tokens=int(raw.get("target_tokens", 24_000) or 24_000),
            soft_warning_tokens=int(
                raw.get("soft_warning_tokens", 26_000) or 26_000
            ),
            auto_compact_tokens=int(
                raw.get("auto_compact_tokens", min(27_000, max_live - 1_000))
                or min(27_000, max_live - 1_000)
            ),
            max_retrieval_tokens=int(raw.get("max_retrieval_tokens", 5_000) or 5_000),
            max_tool_result_tokens=int(raw.get("max_tool_result_tokens", 6_000) or 6_000),
            max_memory_prefetch_tokens=int(
                raw.get("max_memory_prefetch_tokens", 1_500) or 1_500
            ),
        )

    @classmethod
    def load(cls) -> "ContextGovernorConfig":
        try:
            from hermes_cli.config import load_config

            cfg = load_config() or {}
            return cls.from_config_dict(cfg.get("context_governor"))
        except Exception:
            return cls()


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
    # recovery: none = proceed; compact = caller should auto-compress+retry;
    # fail = every in-governor recovery exhausted (caller may still try
    # session continuation before surfacing an error).
    recovery: RecoveryAction = "none"
    blocked: bool = False
    block_reason: str = ""
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
) -> tuple[int, int, int, int]:
    """Return (live_tokens, messages_tokens, tools_tokens, total_tokens).

    *live_tokens* is the compressible budget: messages + memory prefetch.
    Tool schemas are reported separately and must not alone hard-block.
    """
    msgs = list(messages)
    messages_tokens = estimate_messages_tokens_rough(msgs) if msgs else 0
    prefetch_tokens = estimate_tokens_rough(memory_prefetch) if memory_prefetch else 0
    live_tokens = messages_tokens + prefetch_tokens
    tools_list = list(tools) if tools is not None else None
    tools_tokens = 0
    if tools_list:
        # Reuse the shared estimator's tool bucket (total − messages − empty sys).
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
    """Last-resort in-governor shrink: keep system + last user turn.

    Used only after prune + caller compact recovery have already failed.
    """
    if not messages:
        return messages
    out = [dict(m) for m in messages]
    system = [m for m in out if m.get("role") == "system"]
    # Keep the final user message (and any trailing tool/assistant pair after
    # the previous user would be unusual for a blocked turn — keep last user).
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
        # Leave room under budget for a short system prefix.
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
    """Enforce live-transcript budgets with recover-first semantics.

    Parameters
    ----------
    after_recovery:
        True when the caller already ran auto-compression for this pressure
        event. Enables the fail/emergency path instead of asking for compact
        again.
    allow_emergency_truncate:
        When True (and after_recovery), aggressively truncate the transcript
        to system + last user message before declaring failure.
    """
    cfg = config or ContextGovernorConfig()
    tools_list = list(tools) if tools is not None else None
    msgs = [dict(m) for m in messages]
    prefetch = memory_prefetch or ""
    actions: List[str] = []

    live_before, _, tools_tok_before, total_before = _estimate_components(
        msgs, tools_list, prefetch
    )
    tokens_before = live_before  # live budget is the contract

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
            config=cfg,
        )

    prefetch = cap_memory_prefetch(
        prefetch, cfg.max_memory_prefetch_tokens, actions
    )
    msgs = _prune_tool_results(
        msgs,
        max_tool_result_tokens=cfg.max_tool_result_tokens,
        max_retrieval_tokens=cfg.max_retrieval_tokens,
        actions=actions,
    )

    live_after, msg_tok, tools_tok, total_after = _estimate_components(
        msgs, tools_list, prefetch
    )

    # Pressure pass: summarize older tool results more aggressively.
    if live_after > cfg.auto_compact_tokens:
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

    if tools_tok and total_after > cfg.max_live_tokens and live_after <= cfg.max_live_tokens:
        # Fixed tool/schema overhead dominates the *total* request size, but
        # the live transcript fits. Never hard-block for this — /compress
        # cannot shrink tool schemas.
        actions.append(
            f"tools_overhead_outside_live_budget tools≈{tools_tok:,} "
            f"live≈{live_after:,} total≈{total_after:,}"
        )
        logger.info(
            "Context governor: tool schemas ≈%s tokens sit outside the live "
            "transcript budget (live≈%s / max=%s); allowing request",
            f"{tools_tok:,}",
            f"{live_after:,}",
            f"{cfg.max_live_tokens:,}",
        )

    recovery: RecoveryAction = "none"
    blocked = False
    block_reason = ""

    if live_after > cfg.max_live_tokens:
        if not after_recovery:
            recovery = "compact"
            actions.append("recovery_compact_needed")
            logger.info(
                "Context governor: live transcript ≈%s > max %s — requesting "
                "auto-compaction (tools≈%s not counted against live budget)",
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
                    f"governor budget of {cfg.max_live_tokens:,} after automatic "
                    f"recovery. Start a fresh session with /new, or continue in a "
                    f"new working context."
                )
                actions.append("blocked_after_recovery")
                logger.warning(block_reason)
            else:
                actions.append("emergency_truncate_recovered")
                recovery = "none"
    elif live_after > cfg.auto_compact_tokens and not after_recovery:
        # Soft pressure: ask caller to compact proactively, but do not block
        # if compaction is skipped (caller may still send).
        recovery = "compact"
        actions.append("soft_auto_compact")
        logger.info(
            "Context governor: live≈%s crossed auto-compact=%s — requesting compaction",
            f"{live_after:,}",
            f"{cfg.auto_compact_tokens:,}",
        )
    elif live_after > cfg.soft_warning_tokens:
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
        config=cfg,
    )
