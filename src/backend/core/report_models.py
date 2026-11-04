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
    "vllm-qwen3.5:4b",
    "deepseek-flash",
    "huggingface-deepseek-v4-flash",
    "grok-4.3",
]
# The default list stays Ollama and cloud only; the local vLLM model is opted into through
# REPORT_GENERATION_MODELS, because it needs its own GPU server (see docker-compose.yaml).
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
# The output limit of every batch request unless the model or the admin sets another.
DEFAULT_REPORT_OUTPUT_TOKENS: Final = 20_000
# Bounds of the token limits the admin may type; the output warning is advice, not a rule.
MIN_REPORT_INPUT_TOKENS: Final = 1_000
MAX_REPORT_TOKENS: Final = 2_000_000
LOW_REPORT_OUTPUT_TOKENS: Final = 2_000
# Upper bound of the parallel batches the admin can type per report; 0 means no parallelism.
MAX_REPORT_BATCH_WORKERS: Final = 300

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
    # Fixed by the request itself (Ollama num_ctx) and therefore enforced against the output.
    context_tokens: int | None = None
    # The model's own context window, shown to the user; the default of the env setting.
    context_window: int = 32_768
    # The limit of each batch request, not of the whole report.
    max_output_tokens: int = DEFAULT_REPORT_OUTPUT_TOKENS
    # With parallel batches one request may use only this fraction of the context (the server
    # shares its memory between them); batches run one after another may use all of it.
    parallel_context_divisor: int = 1
    effort_control: EffortControl = "none"
    temperature: float | None = None
    repeat_penalty: float | None = None
    repeat_last_n: int | None = None


REPORT_MODELS: Mapping[ReportModel, ReportModelSpec] = MappingProxyType(
    {
        "ollama-gemma4:12b": ReportModelSpec(
            "ollama", "gemma4:12b", context_window=262_144, effort_control="ollama_think"
        ),
        # The 1B model needs constrained sampling to reduce repeated-token loops in JSON.
        "ollama-gemma3:1b": ReportModelSpec(
            "ollama",
            "gemma3:1b",
            context_window=32_768,
            temperature=0.0,
            repeat_penalty=1.1,
            repeat_last_n=256,
        ),
        "ollama-qwen3.5:9b": ReportModelSpec(
            "ollama", "qwen3.5:9b", context_window=262_144, effort_control="ollama_think"
        ),
        "ollama-qwen3.5:4b": ReportModelSpec(
            "ollama", "qwen3.5:4b", context_window=262_144, effort_control="ollama_think"
        ),
        "ollama-ministral-3:8b": ReportModelSpec(
            "ollama", "ministral-3:8b", context_window=262_144
        ),
        "ollama-deepseek-r1:8b": ReportModelSpec(
            "ollama",
            "deepseek-r1:8b",
            batch_max_tokens=24_000,
            context_tokens=32_768,
            context_window=32_768,
            max_output_tokens=8_192,
            effort_control="ollama_think",
        ),
        # Served by the `vllm-report` Compose service under this name. vLLM maps the Responses
        # `reasoning.effort` ("none" switches Qwen's thinking off) to the chat template itself.
        "vllm-qwen3.5:4b": ReportModelSpec(
            "vllm",
            "qwen3.5-4b",
            context_window=131_072,
            parallel_context_divisor=2,
            effort_control="responses_effort",
        ),
        "deepseek-flash": ReportModelSpec(
            "deepseek",
            "deepseek-flash",
            context_window=1_048_576,
            effort_control="responses_effort",
        ),
        "huggingface-deepseek-v4-flash": ReportModelSpec(
            "huggingface",
            "deepseek-ai/DeepSeek-V4-Flash:deepinfra",
            context_window=1_048_576,
            effort_control="responses_effort",
        ),
        "grok-4.3": ReportModelSpec(
            "xai", "grok-4.3", context_window=1_000_000, effort_control="responses_effort"
        ),
    }
)


# Models whose request can carry the effort; the others ignore it.
EFFORT_MODELS: Final[tuple[ReportModel, ...]] = tuple(
    choice for choice, spec in REPORT_MODELS.items() if spec.effort_control != "none"
)


# The context one request may use while batches run in parallel.
def parallel_context_tokens(model: ReportModel, context: int) -> int:
    return context // REPORT_MODELS[model].parallel_context_divisor


# The context one request may use. `workers` is the batches processed at once; 0 and 1 both
# mean one after another, which may use the whole context.
def request_context_tokens(model: ReportModel, context: int, workers: int) -> int:
    return context if workers <= 1 else parallel_context_tokens(model, context)


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
