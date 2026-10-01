"""Per-provider configuration for the Responses API client (AI_PROVIDER)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal
from urllib.parse import urlparse

from medicina_naturista.config import Settings

# How the provider is asked for a JSON object: Responses-style `text.format`,
# Chat-Completions-style `response_format`, or only through the system prompt
# (the parser tolerates Markdown fences and surrounding text).
JsonFormat = Literal["text_format", "response_format"] | None

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal"})


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    label: str
    base_url: str
    model: str
    reasoning_effort: str | None
    api_key: Callable[[], str]
    api_key_env: str
    api_key_required: bool
    json_format: JsonFormat
    send_store: bool
    max_context_chars: int | None
    max_output_tokens: int
    read_timeout_seconds: int
    stream: bool = False


# Whether the URL points at this machine (or the Docker host), where Ollama needs no key.
def _is_local(url: str) -> bool:
    return (urlparse(url).hostname or "") in LOCAL_HOSTS


# The single place where AI_PROVIDER becomes a provider configuration.
def provider_config(settings: Settings) -> ProviderConfig:
    common = {
        "max_output_tokens": settings.ai_max_output_tokens,
        "read_timeout_seconds": settings.ai_read_timeout_seconds,
        "stream": settings.ai_stream,
    }
    if settings.ai_provider == "xai":
        return ProviderConfig(
            name="xai",
            label="xAI",
            base_url=settings.xai_api_base,
            model=settings.xai_model,
            reasoning_effort=settings.xai_reasoning_effort,
            api_key=settings.api_key,
            api_key_env="X_API_KEY",
            api_key_required=True,
            json_format="text_format",
            send_store=True,
            max_context_chars=None,
            **common,
        )
    # DeepSeek's own API documents `text.format` and `reasoning.effort`, and
    # ignores `store` (api-docs.deepseek.com/guides/responses_api).
    if settings.ai_provider == "deepseek":
        return ProviderConfig(
            name="deepseek",
            label="DeepSeek",
            base_url=settings.deepseek_api_base,
            model=settings.deepseek_model,
            reasoning_effort=settings.deepseek_reasoning_effort or None,
            api_key=settings.deepseek_api_key,
            api_key_env="DEEPSEEK_API_KEY",
            api_key_required=True,
            json_format="text_format",
            send_store=False,
            max_context_chars=settings.deepseek_max_context_chars,
            **common,
        )
    # json_format stays None for the two providers below until Phase 0 of
    # architecture/ai-provider-switch-plan.md confirms which field they honor.
    if settings.ai_provider == "huggingface":
        return ProviderConfig(
            name="huggingface",
            label="Hugging Face",
            base_url=settings.hf_api_base,
            model=settings.hf_model,
            reasoning_effort=settings.hf_reasoning_effort or None,
            api_key=settings.hf_token,
            api_key_env="HF_TOKEN",
            api_key_required=True,
            json_format=None,
            send_store=False,
            max_context_chars=settings.hf_max_context_chars,
            **common,
        )
    return ProviderConfig(
        name="ollama",
        label="Ollama",
        base_url=settings.ollama_api_base,
        model=settings.ollama_model,
        reasoning_effort=settings.ollama_reasoning_effort or None,
        api_key=settings.ollama_api_key,
        api_key_env="OLLAMA_API_KEY",
        api_key_required=not _is_local(settings.ollama_api_base),
        json_format=None,
        send_store=False,
        max_context_chars=settings.ollama_max_context_chars,
        **common,
    )
