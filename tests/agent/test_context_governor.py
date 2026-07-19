"""Absolute live-token context governor (Phase 1 context-cost remediation)."""

from agent.context_governor import (
    ContextGovernorConfig,
    govern_request,
)


def _cfg(**overrides):
    base = ContextGovernorConfig(
        enabled=True,
        max_live_tokens=2_000,
        max_retrieval_tokens=400,
        max_tool_result_tokens=500,
        max_memory_prefetch_tokens=200,
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def test_governor_passes_small_request():
    messages = [
        {"role": "system", "content": "You are Hermes."},
        {"role": "user", "content": "Hello"},
    ]
    result = govern_request(
        messages,
        tools=[{"type": "function", "function": {"name": "todo", "parameters": {}}}],
        memory_prefetch="",
        config=_cfg(max_live_tokens=50_000),
    )
    assert result.blocked is False
    assert result.tokens_after <= result.tokens_before
    assert result.messages[-1]["content"] == "Hello"


def test_governor_truncates_memory_prefetch():
    prefetch = "recalled fact " * 5_000  # huge
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]
    result = govern_request(
        messages,
        tools=None,
        memory_prefetch=prefetch,
        config=_cfg(max_memory_prefetch_tokens=50, max_live_tokens=50_000),
    )
    assert result.blocked is False
    assert "memory_prefetch" in " ".join(result.actions)
    # Rough: 50 tokens * 4 chars = 200 chars (+ellipsis room)
    assert len(result.memory_prefetch) < len(prefetch)
    assert len(result.memory_prefetch) <= 50 * 4 + 80


def test_governor_prunes_old_tool_results():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "research"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "web_extract", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "DOC " * 8_000},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c2",
                    "type": "function",
                    "function": {"name": "web_extract", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c2", "content": "MORE " * 8_000},
        {"role": "user", "content": "summarize"},
    ]
    result = govern_request(
        messages,
        tools=None,
        memory_prefetch="",
        config=_cfg(
            max_live_tokens=50_000,
            max_tool_result_tokens=300,
            max_retrieval_tokens=50_000,
        ),
    )
    assert result.blocked is False
    assert any("tool_result" in a for a in result.actions)
    tool_contents = [m["content"] for m in result.messages if m.get("role") == "tool"]
    assert sum(len(c) for c in tool_contents) < sum(
        len(m["content"]) for m in messages if m.get("role") == "tool"
    )


def test_governor_blocks_when_still_over_after_prune():
    # System alone exceeds the live budget; pruning cannot remove system.
    messages = [
        {"role": "system", "content": "S" * 40_000},
        {"role": "user", "content": "hi"},
    ]
    result = govern_request(
        messages,
        tools=None,
        memory_prefetch="",
        config=_cfg(max_live_tokens=500),
    )
    assert result.blocked is True
    assert result.block_reason
    assert result.tokens_after > result.config.max_live_tokens


def test_disabled_governor_is_noop():
    messages = [{"role": "user", "content": "x" * 100_000}]
    result = govern_request(
        messages,
        tools=None,
        memory_prefetch="y" * 10_000,
        config=_cfg(enabled=False, max_live_tokens=10),
    )
    assert result.blocked is False
    assert result.memory_prefetch == "y" * 10_000
    assert result.actions == []
