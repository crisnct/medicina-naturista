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
DEFAULT_REPORT_BATCH_MAX_TOKENS: Final = 25_000

# The user-selected depth of AI reasoning; each provider maps it to its own parameter.
ReportEffort = Literal["low", "medium", "high"]
REPORT_EFFORTS: Final[tuple[ReportEffort, ...]] = ("low", "medium", "high")
DEFAULT_REPORT_EFFORT: Final[ReportEffort] = "low"

# How a model accepts the effort: not at all, as Ollama's boolean `think`, or as the
# Responses API `reasoning.effort` string.
EffortControl = Literal["none", "ollama_think", "responses_effort"]


@dataclass(frozen=True)
class ReportModelSpec:
    provider: str
    model: str
    owner_only: bool = True
    batch_max_tokens: int = DEFAULT_REPORT_BATCH_MAX_TOKENS
    context_tokens: int | None = None
    max_output_tokens: int | None = None
    effort_control: EffortControl = "none"
    temperature: float | None = None
    repeat_penalty: float | None = None
    repeat_last_n: int | None = None


REPORT_MODELS: Mapping[ReportModel, ReportModelSpec] = MappingProxyType(
    {
        "ollama-gemma4:12b": ReportModelSpec("ollama", "gemma4:12b", effort_control="ollama_think"),
        # The 1B model needs constrained sampling to reduce repeated-token loops in JSON.
        "ollama-gemma3:1b": ReportModelSpec(
            "ollama", "gemma3:1b", temperature=0.0, repeat_penalty=1.1, repeat_last_n=256
        ),
        "ollama-qwen3.5:9b": ReportModelSpec("ollama", "qwen3.5:9b", effort_control="ollama_think"),
        "ollama-qwen3.5:4b": ReportModelSpec("ollama", "qwen3.5:4b", effort_control="ollama_think"),
        "ollama-ministral-3:8b": ReportModelSpec("ollama", "ministral-3:8b"),
        "ollama-deepseek-r1:8b": ReportModelSpec(
            "ollama",
            "deepseek-r1:8b",
            batch_max_tokens=24_000,
            context_tokens=32_768,
            max_output_tokens=8_192,
            effort_control="ollama_think",
        ),
        "deepseek-flash": ReportModelSpec(
            "deepseek", "deepseek-flash", effort_control="responses_effort"
        ),
        "huggingface-deepseek-v4-flash": ReportModelSpec(
            "huggingface",
            "deepseek-ai/DeepSeek-V4-Flash:deepinfra",
            effort_control="responses_effort",
        ),
        "grok-4.3": ReportModelSpec("xai", "grok-4.3", effort_control="responses_effort"),
    }
)


# Models whose request can carry the effort; the others ignore it.
EFFORT_MODELS: Final[tuple[ReportModel, ...]] = tuple(
    choice for choice, spec in REPORT_MODELS.items() if spec.effort_control != "none"
)


def parse_report_effort(value: str) -> ReportEffort:
    normalized = value.strip().casefold()
    if normalized not in REPORT_EFFORTS:
        raise ValueError(f"Unsupported report effort; expected one of {', '.join(REPORT_EFFORTS)}")
    return cast(ReportEffort, normalized)


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
