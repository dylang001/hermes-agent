"""Alibaba Cloud DashScope provider profile."""

from agent.prompt_cache_capabilities import PromptCacheCapability, explicit_envelope
from providers import register_provider
from providers.base import ProviderProfile


class AlibabaProfile(ProviderProfile):
    """DashScope OpenAI-compatible wire — Qwen needs explicit cache markers."""

    def prompt_cache_capability(
        self,
        *,
        api_mode: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> PromptCacheCapability | None:
        # pi-mono #3392 / #3393: DashScope Qwen returns zero cache hits
        # without Anthropic-style markers on the OpenAI wire.
        return explicit_envelope("profile:alibaba+qwen_openai_wire")


alibaba = AlibabaProfile(
    name="alibaba",
    aliases=("dashscope", "alibaba-cloud", "qwen-dashscope"),
    env_vars=("DASHSCOPE_API_KEY",),
    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
)

register_provider(alibaba)
