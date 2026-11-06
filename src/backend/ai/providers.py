"""Per-provider transport settings for report generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, TypedDict
from urllib.parse import urlparse

from backend.config import Settings
from backend.core.report_models import (
    DEFAULT_REPORT_OUTPUT_TOKENS,
    REPORT_MODELS,
    EffortControl,
    ReportModel,
    parallel_context_divisor,
)

# How the provider is asked for a JSON object: Responses-style `text.format`,
# Chat-Completions-style `response_format`, or only through the system prompt
# (the parser tolerates Markdown fences and surrounding text).
JsonFormat = Literal["text_format", "response_format"] | None

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal"})


class _GenerationLimits(TypedDict):
    max_output_tokens: int
    read_timeout_seconds: int
    stream: bool
    parallel_context_divisor: int


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
    repeat_penalty: float | None = None
    repeat_last_n: int | None = None
    # How a report request carries the user-selected effort; classifiers keep "none".
    effort_control: EffortControl = "none"
    # With parallel batches a request may use this fraction of the context (see the catalog).
    parallel_context_divisor: int = 1


# Whether the URL points at this machine (or the Docker host), where Ollama needs no key.
def _is_local(url: str) -> bool:
    return (urlparse(url).hostname or "") in LOCAL_HOSTS


# The output limit of each batch request of a report model: the Ollama per-model override,
# else the catalog value. The report panel shows it as the default.
def default_max_output_tokens(settings: Settings, model: ReportModel) -> int:
    spec = REPORT_MODELS[model]
    if spec.provider == "ollama":
        return settings.ollama_max_output_tokens_by_model.get(model, spec.max_output_tokens)
    return spec.max_output_tokens


# The catalog entry of the model the settings select, if it is one of the report choices.
def _catalog_choice(settings: Settings) -> ReportModel | None:
    selected = {
        "xai": settings.xai_model,
        "deepseek": settings.deepseek_model,
        "huggingface": settings.hf_model,
        "vllm": settings.vllm_model,
    }.get(settings.ai_provider, settings.ollama_model)
    return next(
        (
            choice
            for choice, spec in REPORT_MODELS.items()
            if spec.provider == settings.ai_provider and spec.model == selected
        ),
        None,
    )


# Generic constructor settings; report choices are resolved by the shared model catalog.
def provider_config(settings: Settings) -> ProviderConfig:
    choice = _catalog_choice(settings)
    common: _GenerationLimits = {
        "max_output_tokens": default_max_output_tokens(settings, choice)
        if choice is not None
        else DEFAULT_REPORT_OUTPUT_TOKENS,
        "read_timeout_seconds": settings.ai_read_timeout_seconds,
        "stream": settings.ai_stream,
        "parallel_context_divisor": parallel_context_divisor(choice) if choice is not None else 1,
    }
    if settings.ai_provider == "xai":
        return ProviderConfig(
            name="xai",
            label="xAI",
            base_url=settings.xai_api_base,
            model=settings.xai_model,
            reasoning_effort=None,
            api_key=settings.api_key,
            api_key_env="X_API_KEY",
            api_key_required=True,
            json_format="text_format",
            send_store=True,
            max_context_chars=0,
            effort_control="responses_effort",
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
            reasoning_effort=None,
            api_key=settings.deepseek_api_key,
            api_key_env="DEEPSEEK_API_KEY",
            api_key_required=True,
            json_format="text_format",
            send_store=False,
            max_context_chars=0,
            effort_control="responses_effort",
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
            reasoning_effort=None,
            api_key=settings.hf_token,
            api_key_env="HF_TOKEN",
            api_key_required=True,
            json_format=None,
            send_store=False,
            max_context_chars=0,
            effort_control="responses_effort",
            **common,
        )
    # The local vLLM server. Its report client (VllmReportClient in client.py) sends Chat
    # Completions, the vLLM API that caps the thinking; the grammar is requested per report.
    if settings.ai_provider == "vllm":
        return ProviderConfig(
            name="vllm",
            label="vLLM",
            base_url=settings.vllm_api_base,
            model=settings.vllm_model,
            reasoning_effort=None,
            api_key=lambda: "",
            api_key_env="VLLM_API_KEY",
            api_key_required=False,
            json_format=None,
            send_store=False,
            max_context_chars=0,
            effort_control="responses_effort",
            **common,
        )
    context_tokens = None
    effort_control: EffortControl = "none"
    temperature = None
    repeat_penalty = None
    repeat_last_n = None
    if choice is not None:
        context_tokens = REPORT_MODELS[choice].context_tokens
        effort_control = REPORT_MODELS[choice].effort_control
        temperature = REPORT_MODELS[choice].temperature
        repeat_penalty = REPORT_MODELS[choice].repeat_penalty
        repeat_last_n = REPORT_MODELS[choice].repeat_last_n
    return ProviderConfig(
        name="ollama",
        label="Ollama",
        base_url=settings.ollama_api_base,
        keep_alive_seconds=settings.ollama_keep_alive_seconds,
        model=settings.ollama_model,
        reasoning_effort=None,
        api_key=settings.ollama_api_key,
        api_key_env="OLLAMA_API_KEY",
        api_key_required=not _is_local(settings.ollama_api_base),
        json_format=None,
        send_store=False,
        max_context_chars=0,
        context_tokens=context_tokens,
        effort_control=effort_control,
        temperature=temperature,
        repeat_penalty=repeat_penalty,
        repeat_last_n=repeat_last_n,
        **common,
    )
