"""Supported report choices and their immutable provider routing."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, Mapping, cast

ReportModel = Literal[
    "ollama-gemma4:12b",
    "ollama-gemma3:1b",
    "ollama-qwen3.5:9b",
    "ollama-qwen3.5:4b",
    "ollama-ministral-3:8b",
    "ollama-deepseek-r1:8b",
    "deepseek-flash",
    "huggingface-deepseek-v4-flash",
    "grok-4.3",
]
DEFAULT_REPORT_MODELS: tuple[ReportModel, ...] = (
    "ollama-gemma3:1b",
    "ollama-gemma4:12b",
    "ollama-ministral-3:8b",
    "ollama-qwen3.5:9b",
    "ollama-qwen3.5:4b",
    "ollama-deepseek-r1:8b",
    "deepseek-flash",
    "huggingface-deepseek-v4-flash",
    "grok-4.3",
)
DEFAULT_REPORT_MODEL: ReportModel = DEFAULT_REPORT_MODELS[0]
DEFAULT_REPORT_BATCH_MAX_CHARS: Final = 25_000


@dataclass(frozen=True)
class ReportModelSpec:
    provider: str
    model: str
    owner_only: bool = True
    batch_max_chars: int = DEFAULT_REPORT_BATCH_MAX_CHARS
    context_tokens: int | None = None
    max_output_tokens: int | None = None
    thinking: bool | None = None


REPORT_MODELS: Mapping[ReportModel, ReportModelSpec] = MappingProxyType(
    {
        "ollama-gemma4:12b": ReportModelSpec("ollama", "gemma4:12b"),
        "ollama-gemma3:1b": ReportModelSpec("ollama", "gemma3:1b"),
        "ollama-qwen3.5:9b": ReportModelSpec("ollama", "qwen3.5:9b"),
        "ollama-qwen3.5:4b": ReportModelSpec("ollama", "qwen3.5:4b"),
        "ollama-ministral-3:8b": ReportModelSpec("ollama", "ministral-3:8b"),
        "ollama-deepseek-r1:8b": ReportModelSpec(
            "ollama",
            "deepseek-r1:8b",
            batch_max_chars=8_000,
            context_tokens=16_384,
            max_output_tokens=8_192,
            thinking=True,
        ),
        "deepseek-flash": ReportModelSpec("deepseek", "deepseek-flash"),
        "huggingface-deepseek-v4-flash": ReportModelSpec(
            "huggingface", "deepseek-ai/DeepSeek-V4-Flash:deepinfra"
        ),
        "grok-4.3": ReportModelSpec("xai", "grok-4.3"),
    }
)


def parse_report_model(value: str) -> ReportModel:
    normalized = value.strip().casefold()
    if normalized not in REPORT_MODELS:
        raise ValueError(f"Unsupported report model; expected one of {', '.join(REPORT_MODELS)}")
    return cast(ReportModel, normalized)


def parse_report_models(value: str) -> tuple[ReportModel, ...]:
    """Parse an ordered, nonempty CSV without silently changing its contents."""
    parts = [part.strip() for part in value.split(",")]
    if any(not part for part in parts):
        raise ValueError("REPORT_GENERATION_MODELS must be a nonempty CSV without empty entries")
    try:
        models = tuple(parse_report_model(part) for part in parts)
    except ValueError as exc:
        raise ValueError(f"REPORT_GENERATION_MODELS: {exc}") from None
    if len(set(models)) != len(models):
        raise ValueError("REPORT_GENERATION_MODELS must not contain duplicate models")
    return models
