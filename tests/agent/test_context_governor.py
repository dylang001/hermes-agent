"""Live-transcript context governor — recover-first semantics."""

from agent.context_governor import (
    ContextGovernorConfig,
    govern_request,
)


def _cfg(**overrides):
    base = ContextGovernorConfig(
        enabled=True,
        max_live_tokens=2_000,
        target_tokens=1_200,
        soft_warning_tokens=1_500,
        auto_compact_tokens=1_800,
        max_retrieval_tokens=400,
        max_tool_result_tokens=500,
        max_memory_prefetch_tokens=200,
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _huge_tools(n: int = 80):
    """Synthetic tool schemas large enough to dominate a request estimate."""
    tools = []
    for i in range(n):
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": f"tool_{i}",
                    "description": ("x" * 1200) + f" tool number {i}",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "q": {
                                "type": "string",
                                "description": "y" * 800,
                            }
                        },
                    },
                },
            }
        )
    return tools


def test_governor_passes_small_request():
    messages = [
        {"role": "system", "content": "You are Hermes."},
        {"role": "user", "content": "Hello"},
    ]
    result = govern_request(
        messages,
        tools=[{"type": "function", "function": {"name": "todo", "parameters": {}}}],
        memory_prefetch="",
        config=_cfg(max_live_tokens=50_000, auto_compact_tokens=49_000),
    )
    assert result.blocked is False
    assert result.recovery == "none"
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
            auto_compact_tokens=49_000,
            max_tool_result_tokens=300,
            max_retrieval_tokens=50_000,
        ),
    )
    assert result.blocked is False
    assert any("tool_result" in a for a in result.actions)
    tool_contents = [m["content"] for m in result.messages if m.get("role") == "tool"]
    assert sum(len(c) for c in tool_contents) < sum(
        len(m["content"] or "") for m in messages if m.get("role") == "tool"
    )


def test_tool_schema_overhead_never_hard_blocks_hello():
    """Regression: Telegram Hello blocked at 28015/28000 while /compress saw ~1.5k.

    Tool schemas dominated the old total; the live transcript was tiny.
    """
    messages = [
        {"role": "system", "content": "You are Hermes."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi!"},
        {"role": "user", "content": "Hello"},
    ]
    tools = _huge_tools(100)
    result = govern_request(
        messages,
        tools=tools,
        memory_prefetch="",
        config=_cfg(
            max_live_tokens=28_000,
            auto_compact_tokens=27_000,
            soft_warning_tokens=26_000,
        ),
    )
    assert result.blocked is False
    assert result.recovery == "none"
    assert result.tokens_after < 5_000  # live transcript only
    assert result.tokens_tools > 28_000  # schemas dominate total
    assert result.tokens_total > result.config.max_live_tokens
    assert any("tools_overhead" in a for a in result.actions)


def test_live_overage_requests_compact_not_block():
    messages = [
        {"role": "system", "content": "S" * 40_000},
        {"role": "user", "content": "hi"},
    ]
    result = govern_request(
        messages,
        tools=None,
        memory_prefetch="",
        config=_cfg(max_live_tokens=500, auto_compact_tokens=400),
        after_recovery=False,
    )
    assert result.blocked is False
    assert result.recovery == "compact"
    assert result.tokens_after > result.config.max_live_tokens


def test_after_recovery_emergency_truncate_then_pass_or_fail():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "old " * 5_000},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "Hello"},
    ]
    result = govern_request(
        messages,
        tools=None,
        memory_prefetch="",
        config=_cfg(max_live_tokens=800, auto_compact_tokens=700),
        after_recovery=True,
        allow_emergency_truncate=True,
    )
    # Emergency truncate keeps system + last user ("Hello") → should fit.
    assert result.blocked is False
    assert result.recovery == "none"
    assert any("emergency" in a for a in result.actions)
    assert result.messages[-1]["content"] == "Hello"


def test_unrecoverable_still_blocks_after_emergency():
    # System alone cannot fit even after emergency truncate of user turns.
    messages = [
        {"role": "system", "content": "S" * 40_000},
        {"role": "user", "content": "hi"},
    ]
    result = govern_request(
        messages,
        tools=None,
        memory_prefetch="",
        config=_cfg(max_live_tokens=500, auto_compact_tokens=400),
        after_recovery=True,
        allow_emergency_truncate=True,
    )
    assert result.blocked is True
    assert result.recovery == "fail"
    assert result.block_reason
    assert "after automatic recovery" in result.block_reason


def test_disabled_governor_is_noop():
    messages = [{"role": "user", "content": "x" * 100_000}]
    result = govern_request(
        messages,
        tools=None,
        memory_prefetch="y" * 10_000,
        config=_cfg(enabled=False, max_live_tokens=10),
    )
    assert result.blocked is False
    assert result.recovery == "none"
    assert result.memory_prefetch == "y" * 10_000
    assert result.actions == []
