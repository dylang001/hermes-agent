"""Absolute live-token context governor (Phase 1 context-cost remediation).

Unlike compression.threshold (a fraction of the model window), this governor
enforces a hard live-input budget independent of context_length. Oversized
requests are pruned/summarized before the provider call; if still over budget
the request is **blocked** — never silently sent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from agent.model_metadata import (
    estimate_request_tokens_rough,
    estimate_tokens_rough,
)

logger = logging.getLogger(__name__)

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
    """Hard budgets for a single provider request."""

    enabled: bool = True
    max_live_tokens: int = 28_000
    max_retrieval_tokens: int = 5_000
    max_tool_result_tokens: int = 6_000
    max_memory_prefetch_tokens: int = 1_500

    @classmethod
    def from_config_dict(cls, raw: Optional[Dict[str, Any]]) -> "ContextGovernorConfig":
        raw = raw or {}
        if not isinstance(raw, dict):
            return cls()
        return cls(
            enabled=bool(raw.get("enabled", True)),
            max_live_tokens=int(raw.get("max_live_tokens", 28_000) or 28_000),
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
    actions: List[str] = field(default_factory=list)
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
    # Collect tool message indices oldest→newest.
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

    # Protect the most recent tool result; prune older ones.
    protect_newest = 1
    prune_order = tool_idxs[:-protect_newest] if len(tool_idxs) > protect_newest else tool_idxs[:]
    for i in prune_order:
        if _budget_ok():
            break
        content = _msg_content(out[i])
        if not content or content.startswith("["):
            continue
        name = _tool_name_for_result(out, out[i])
        _set_msg_content(out[i], _summarize_tool_content(name, content))
        actions.append(f"tool_result summarized ({name or 'tool'})")

    # If still over, truncate the newest tool result too.
    if not _budget_ok() and tool_idxs:
        i = tool_idxs[-1]
        content = _msg_content(out[i])
        name = _tool_name_for_result(out, out[i])
        # Split remaining budget roughly.
        remain = max(80, max_tool_result_tokens // 2)
        if name in _RETRIEVAL_TOOLS:
            remain = min(remain, max(80, max_retrieval_tokens // 2))
        _set_msg_content(out[i], _truncate_text(content, remain, f"{name or 'tool'}-result"))
        actions.append(f"tool_result truncated newest ({name or 'tool'})")

    return out


def _estimate(
    messages: Sequence[Dict[str, Any]],
    tools: Optional[Sequence[Any]],
    memory_prefetch: str,
) -> int:
    # Memory prefetch is injected into the current user message at send time;
    # include it in the estimate so we don't under-count.
    msgs = list(messages)
    if memory_prefetch and msgs:
        # Shallow estimate: add prefetch tokens on top.
        base = estimate_request_tokens_rough(msgs, tools=tools)
        return base + estimate_tokens_rough(memory_prefetch)
    return estimate_request_tokens_rough(msgs, tools=tools)


def govern_request(
    messages: Sequence[Dict[str, Any]],
    *,
    tools: Optional[Sequence[Any]] = None,
    memory_prefetch: str = "",
    config: Optional[ContextGovernorConfig] = None,
) -> GovernorResult:
    """Enforce absolute live-token budgets. May mutate/prune; may block."""
    cfg = config or ContextGovernorConfig()
    tools_list = list(tools) if tools is not None else None
    msgs = [dict(m) for m in messages]
    prefetch = memory_prefetch or ""
    actions: List[str] = []

    tokens_before = _estimate(msgs, tools_list, prefetch)

    if not cfg.enabled:
        return GovernorResult(
            messages=msgs,
            tools=tools_list,
            memory_prefetch=prefetch,
            tokens_before=tokens_before,
            tokens_after=tokens_before,
            actions=[],
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

    tokens_after = _estimate(msgs, tools_list, prefetch)

    # Second pass: if still over live budget, summarize ALL non-protected
    # tool results more aggressively (keep last 2 user/assistant turns).
    if tokens_after > cfg.max_live_tokens:
        tool_idxs = [i for i, m in enumerate(msgs) if m.get("role") == "tool"]
        for i in tool_idxs[:-1]:
            content = _msg_content(msgs[i])
            if content and "summarized by context governor" not in content:
                name = _tool_name_for_result(msgs, msgs[i])
                _set_msg_content(msgs[i], _summarize_tool_content(name, content))
                actions.append(f"tool_result force-summarized ({name or 'tool'})")
        tokens_after = _estimate(msgs, tools_list, prefetch)

    blocked = tokens_after > cfg.max_live_tokens
    block_reason = ""
    if blocked:
        block_reason = (
            f"Live context ~{tokens_after:,} tokens exceeds absolute governor "
            f"limit of {cfg.max_live_tokens:,}. Request blocked — prune history "
            f"with /compress or /new, or raise context_governor.max_live_tokens."
        )
        actions.append("blocked_oversized_request")
        logger.warning(block_reason)

    return GovernorResult(
        messages=msgs,
        tools=tools_list,
        memory_prefetch=prefetch,
        tokens_before=tokens_before,
        tokens_after=tokens_after,
        actions=actions,
        blocked=blocked,
        block_reason=block_reason,
        config=cfg,
    )
