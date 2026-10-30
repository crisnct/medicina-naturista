"""Per-provider transport settings for report generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, TypedDict
from urllib.parse import urlparse

from backend.config import Settings
from backend.core.report_models import REPORT_MODELS

# How the provider is asked for a JSON object: Responses-style `text.format`,
# Chat-Completions-style `response_format`, or only through the system prompt
# (the parser tolerates Markdown fences and surrounding text).
JsonFormat = Literal["text_format", "response_format"] | None

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal"})


class _GenerationLimits(TypedDict):
    max_output_tokens: int
    read_timeout_seconds: int
    stream: bool


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
    max_context_chars: int
    max_output_tokens: int
    read_timeout_seconds: int
    stream: bool = False
    # Sampling temperature sent with the request; None leaves the provider's default.
    temperature: float | None = None
    response_schema: dict[str, Any] | None = None
    context_tokens: int | None = None
    thinking: bool | None = None
    keep_alive_seconds: int | None = None
    max_content_tokens: int | None = None
    repeat_penalty: float | None = None
    repeat_last_n: int | None = None


# Whether the URL points at this machine (or the Docker host), where Ollama needs no key.
def _is_local(url: str) -> bool:
    return (urlparse(url).hostname or "") in LOCAL_HOSTS


# Generic constructor settings; report choices are resolved by the shared model catalog.
def provider_config(settings: Settings) -> ProviderConfig:
    common: _GenerationLimits = {
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
            max_context_chars=0,
            max_content_tokens=settings.xai_max_content_tokens,
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
            max_context_chars=0,
            max_content_tokens=settings.deepseek_max_content_tokens,
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
            max_context_chars=0,
            max_content_tokens=settings.hf_max_content_tokens,
            **common,
        )
    choice = next(
        (
            choice
            for choice, spec in REPORT_MODELS.items()
            if spec.provider == "ollama" and spec.model == settings.ollama_model
        ),
        None,
    )
    context_tokens = None
    thinking = None
    temperature = None
    repeat_penalty = None
    repeat_last_n = None
    if choice is not None:
        context_tokens = REPORT_MODELS[choice].context_tokens
        common["max_output_tokens"] = settings.ollama_max_output_tokens_by_model.get(
            choice, common["max_output_tokens"]
        )
        thinking = REPORT_MODELS[choice].thinking
        temperature = REPORT_MODELS[choice].temperature
        repeat_penalty = REPORT_MODELS[choice].repeat_penalty
        repeat_last_n = REPORT_MODELS[choice].repeat_last_n
    # Preserve the existing optional boolean control for these model families.
    if settings.ollama_reasoning_effort and settings.ollama_model.startswith(
        ("gemma4:", "qwen3.5:")
    ):
        thinking = settings.ollama_reasoning_effort != "none"
    return ProviderConfig(
        name="ollama",
        label="Ollama",
        base_url=settings.ollama_api_base,
        keep_alive_seconds=settings.ollama_keep_alive_seconds,
        model=settings.ollama_model,
        reasoning_effort=settings.ollama_reasoning_effort or None,
        api_key=settings.ollama_api_key,
        api_key_env="OLLAMA_API_KEY",
        api_key_required=not _is_local(settings.ollama_api_base),
        json_format=None,
        send_store=False,
        max_context_chars=0,
        max_content_tokens=settings.ollama_max_content_tokens,
        context_tokens=context_tokens,
        thinking=thinking,
        temperature=temperature,
        repeat_penalty=repeat_penalty,
        repeat_last_n=repeat_last_n,
        **common,
    )
