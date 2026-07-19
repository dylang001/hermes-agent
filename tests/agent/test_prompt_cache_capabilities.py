"""Tests for the transport/provider prompt-cache capability layer."""

from agent.prompt_cache_capabilities import (
    PromptCacheLayout,
    PromptCacheMode,
    resolve_prompt_cache_capability,
)


class TestTransportDrivenResolution:
    def test_opencode_go_anthropic_wire_is_explicit_native(self):
        cap = resolve_prompt_cache_capability(
            provider="opencode-go",
            base_url="https://opencode.ai/zen/go/v1",
            api_mode="anthropic_messages",
            model="anything",
        )
        assert cap.mode is PromptCacheMode.EXPLICIT
        assert cap.layout is PromptCacheLayout.NATIVE
        assert cap.emit_explicit_markers is True

    def test_opencode_go_openai_wire_is_auto(self):
        cap = resolve_prompt_cache_capability(
            provider="opencode-go",
            base_url="https://opencode.ai/zen/go/v1",
            api_mode="chat_completions",
            model="glm-5.2",
        )
        assert cap.mode is PromptCacheMode.AUTO
        assert cap.emit_explicit_markers is False

    def test_opencode_go_qwen_openai_wire_is_explicit_envelope(self):
        cap = resolve_prompt_cache_capability(
            provider="opencode-go",
            base_url="https://opencode.ai/zen/go/v1",
            api_mode="chat_completions",
            model="qwen3.6-plus",
        )
        assert cap.mode is PromptCacheMode.EXPLICIT
        assert cap.layout is PromptCacheLayout.ENVELOPE

    def test_minimax_direct_anthropic_is_explicit(self):
        cap = resolve_prompt_cache_capability(
            provider="minimax",
            base_url="https://api.minimax.io/anthropic",
            api_mode="anthropic_messages",
            model="MiniMax-M2.7",
        )
        assert cap.mode is PromptCacheMode.EXPLICIT
        assert cap.layout is PromptCacheLayout.NATIVE

    def test_minimax_direct_openai_wire_is_auto(self):
        cap = resolve_prompt_cache_capability(
            provider="minimax",
            base_url="https://api.minimax.io/v1",
            api_mode="chat_completions",
            model="minimax-m2.7",
        )
        assert cap.mode is PromptCacheMode.AUTO
        assert cap.emit_explicit_markers is False

    def test_anthropic_native_is_explicit(self):
        cap = resolve_prompt_cache_capability(
            provider="anthropic",
            base_url="https://api.anthropic.com",
            api_mode="anthropic_messages",
            model="claude-sonnet-4",
        )
        assert cap.mode is PromptCacheMode.EXPLICIT
        assert cap.layout is PromptCacheLayout.NATIVE

    def test_openrouter_claude_is_explicit_envelope(self):
        cap = resolve_prompt_cache_capability(
            provider="openrouter",
            base_url="https://openrouter.ai/api/v1",
            api_mode="chat_completions",
            model="anthropic/claude-sonnet-4",
        )
        assert cap.mode is PromptCacheMode.EXPLICIT
        assert cap.layout is PromptCacheLayout.ENVELOPE

    def test_openrouter_gpt_is_auto_no_markers(self):
        cap = resolve_prompt_cache_capability(
            provider="openrouter",
            base_url="https://openrouter.ai/api/v1",
            api_mode="chat_completions",
            model="openai/gpt-5.4",
        )
        assert cap.mode is PromptCacheMode.AUTO
        assert cap.emit_explicit_markers is False

    def test_openrouter_qwen_is_auto_no_markers(self):
        # OpenRouter Qwen uses upstream provider caching — not Hermes markers.
        cap = resolve_prompt_cache_capability(
            provider="openrouter",
            base_url="https://openrouter.ai/api/v1",
            api_mode="chat_completions",
            model="qwen/qwen3-coder",
        )
        assert cap.mode is PromptCacheMode.AUTO
        assert cap.emit_explicit_markers is False

    def test_default_openai_wire_never_emits_markers(self):
        cap = resolve_prompt_cache_capability(
            provider="custom",
            base_url="https://api.fireworks.ai/inference/v1",
            api_mode="chat_completions",
            model="claude-sonnet-4",
        )
        assert cap.emit_explicit_markers is False
