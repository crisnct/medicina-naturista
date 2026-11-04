"""Environment-backed settings. No patient data belongs in configuration or logs."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Literal
from urllib.parse import urlsplit

from dotenv import load_dotenv

from backend.core.report_models import (
    DEFAULT_REPORT_EFFORT,
    DEFAULT_REPORT_MODEL,
    DEFAULT_REPORT_MODELS,
    MIN_REPORT_INPUT_TOKENS,
    REPORT_EFFORTS,
    REPORT_MODELS,
    ReportEffort,
    ReportModel,
    parse_report_models,
)
from backend.core.score_formula import DEFAULT_FORMULA, compile_formula

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DATA_DIR = ROOT / "medicina-naturista-documente" / "data"


ENV_NAME = "REPORT_GENERATION_BATCH_MAX_TOKENS_BY_MODEL"
_LIMIT_KEYS = frozenset({"tokens", "context", "effort"})


def _default_context() -> Mapping[ReportModel, int]:
    return MappingProxyType({model: spec.context_window for model, spec in REPORT_MODELS.items()})


def _default_effort() -> Mapping[ReportModel, ReportEffort]:
    return MappingProxyType({model: DEFAULT_REPORT_EFFORT for model in REPORT_MODELS})


# One JSON object per model: {"tokens": batch input budget, "context": the model's context
# window, "effort": the effort preselected in the report panel}. Only "tokens" is required;
# the others fall back to the catalog. The three results are immutable, like the provider snapshot.
def _model_limits(
    value: str | None = None,
) -> tuple[
    Mapping[ReportModel, int], Mapping[ReportModel, int], Mapping[ReportModel, ReportEffort]
]:
    def unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"{ENV_NAME} contains duplicate keys")
            result[key] = item
        return result

    tokens = MappingProxyType(
        {model: spec.batch_max_tokens for model, spec in REPORT_MODELS.items()}
    )
    if value is None or not value.strip():
        return tokens, _default_context(), _default_effort()
    try:
        parsed = json.loads(value, object_pairs_hook=unique_pairs)
    except (ValueError, TypeError):
        raise ValueError(f"{ENV_NAME} must be a JSON object with unique model keys") from None
    if not isinstance(parsed, dict):
        raise ValueError(f"{ENV_NAME} must be a JSON object")
    # Like REPORT_GENERATION_MODELS, the model names are matched without regard to case.
    folded = {key.strip().casefold(): item for key, item in parsed.items()}
    if len(folded) != len(parsed):
        raise ValueError(f"{ENV_NAME} contains duplicate keys")
    parsed = folded
    if parsed.keys() - REPORT_MODELS.keys():
        raise ValueError("Report batch limits contain an unsupported model")
    tokens_result: dict[ReportModel, int] = {}
    context_result = dict(_default_context())
    effort_result = dict(_default_effort())
    for model in REPORT_MODELS:
        if model not in parsed:
            continue
        entry = parsed[model]
        if not isinstance(entry, dict) or entry.keys() - _LIMIT_KEYS or "tokens" not in entry:
            raise ValueError(
                f'{ENV_NAME} entries must be objects like {{"tokens": 25000, "context": 262144, '
                '"effort": "low"}; "tokens" is required'
            )
        for key, target in (("tokens", tokens_result), ("context", context_result)):
            if key in entry:
                limit = entry[key]
                if type(limit) is not int or limit <= 0:
                    raise ValueError(f"Report model {key} must be a positive integer")
                target[model] = limit
        if "effort" in entry:
            effort = entry["effort"]
            if not isinstance(effort, str) or effort not in REPORT_EFFORTS:
                raise ValueError(f"Report model effort must be one of {', '.join(REPORT_EFFORTS)}")
            effort_result[model] = effort
    return (
        MappingProxyType(tokens_result),
        MappingProxyType(context_result),
        MappingProxyType(effort_result),
    )


# Freeze validated Ollama output limits before any clients are constructed.
def _freeze_ollama_output_limits(limits: Mapping[ReportModel, int]) -> Mapping[ReportModel, int]:
    if not isinstance(limits, Mapping) or any(
        model not in REPORT_MODELS
        or REPORT_MODELS[model].provider != "ollama"
        or type(limit) is not int
        or limit <= 0
        for model, limit in limits.items()
    ):
        raise ValueError(
            "OLLAMA_MAX_OUTPUT_TOKENS_BY_MODEL must map supported Ollama models to positive integers"
        )
    return MappingProxyType(dict(limits))


# Missing keys inherit catalog defaults; duplicate JSON keys never silently win.
def _ollama_output_limits(value: str | None) -> Mapping[ReportModel, int]:
    name = "OLLAMA_MAX_OUTPUT_TOKENS_BY_MODEL"
    defaults = {
        model: spec.max_output_tokens
        for model, spec in REPORT_MODELS.items()
        if spec.provider == "ollama" and spec.max_output_tokens is not None
    }
    if not value or not value.strip():
        return _freeze_ollama_output_limits(defaults)

    def unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"{name} contains duplicate keys")
            result[key] = item
        return result

    try:
        parsed = json.loads(value, object_pairs_hook=unique_pairs)
    except (ValueError, TypeError):
        raise ValueError(f"{name} must be a JSON object with unique model keys") from None
    if not isinstance(parsed, dict):
        raise ValueError(f"{name} must be a JSON object")
    return _freeze_ollama_output_limits(defaults | parsed)


# Read an integer setting and reject values outside its safety bounds.
def _int(
    name: str,
    default: int,
    minimum: int = 1,
    maximum: int | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    value = int((env or {}).get(name, str(default)))
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return value


# Parse a human-friendly boolean environment variable with strict validation.
def _bool(name: str, default: bool, env: Mapping[str, str] | None = None) -> bool:
    value = (env or {}).get(name)
    if value is None:
        return default
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


# Conservative output estimate behind the batch-size checks: a prompt-required minimum of seven
# bilingual messages per product at about 120 tokens each, plus a fixed envelope reserve.
SAFETY_MIN_MESSAGES = 7
SAFETY_TOKENS_PER_MESSAGE = 120
SAFETY_OUTPUT_RESERVE = 512


@dataclass(frozen=True)
class SafetyScope:
    mode: Literal["off", "all", "first", "latin"]
    count: int = 0
    latins: tuple[str, ...] = ()


# Normalised Latin name used to resolve scoped products without guessing between species.
def normalize_latin(value: str) -> str:
    return " ".join(value.split()).casefold()


# HERB_SAFETY_EXTENSION_PRODUCTS: empty (off), `all`, `first:N` or a CSV of exact Latin names.
def parse_safety_scope(raw: str) -> SafetyScope:
    value = raw.strip()
    if not value:
        return SafetyScope("off")
    if value.casefold() == "all":
        return SafetyScope("all")
    if value.casefold().startswith("first:"):
        count = value[6:].strip()
        if not count.isascii() or not count.isdigit() or int(count) <= 0:
            raise ValueError("HERB_SAFETY_EXTENSION_PRODUCTS first:N needs a positive integer")
        return SafetyScope("first", count=int(count))
    names = [normalize_latin(part) for part in value.split(",")]
    if not all(names):
        raise ValueError("HERB_SAFETY_EXTENSION_PRODUCTS contains an empty Latin name")
    return SafetyScope("latin", latins=tuple(dict.fromkeys(names)))


def safety_output_estimate(batch_size: int) -> int:
    return batch_size * SAFETY_MIN_MESSAGES * SAFETY_TOKENS_PER_MESSAGE + SAFETY_OUTPUT_RESERVE


EMBEDDING_DEVICES = ("cpu", "cuda")


# Read EMBEDDING_DEVICE and reject anything that is not a known device.
def _embedding_device(env: Mapping[str, str] | None = None) -> str:
    device = (env or {}).get("EMBEDDING_DEVICE", "cpu").strip().casefold()
    if device not in EMBEDDING_DEVICES:
        raise ValueError(f"EMBEDDING_DEVICE must be one of {', '.join(EMBEDDING_DEVICES)}")
    return device


AI_PROVIDERS = ("xai", "huggingface", "ollama", "deepseek", "vllm")


# Validate the provider used by generic Python client constructors, not an env selector.
def _ai_provider(value: str = "xai") -> str:
    provider = value.strip().casefold()
    if provider not in AI_PROVIDERS:
        raise ValueError(f"AI provider must be one of {', '.join(AI_PROVIDERS)}")
    return provider


@dataclass(frozen=True)
class Settings:
    documents_dir: Path = CORPUS_DATA_DIR / "documents" / "ro"
    documents_en_dir: Path = CORPUS_DATA_DIR / "documents" / "en"
    herb_images_dir: Path = CORPUS_DATA_DIR / "images"
    model_cache_dir: Path = ROOT / "model_cache"
    # Threads of the ONNX embedding model. Few threads beat all cores on hybrid
    # (P/E-core) CPUs, so the default is 8, capped at the machine's core count.
    embedding_threads: int = min(8, os.cpu_count() or 8)
    # Device of the index build's embedding model: "cpu" (FastEmbed) or "cuda"
    # (PyTorch fp16, needs the GPU environment). Queries always run on the CPU.
    embedding_device: str = "cpu"
    frontend_dist_dir: Path = ROOT / "src" / "frontend" / "dist"
    database_url: str = field(
        default="postgresql://medicina:medicina@127.0.0.1:5432/medicina", repr=False
    )
    database_bootstrap_url: str = field(default="", repr=False)
    temp_dir: Path = Path(
        "/tmp/naturist-sessions" if os.name != "nt" else str(ROOT / "var" / "sessions")
    )
    report_generation_models: tuple[ReportModel, ...] = DEFAULT_REPORT_MODELS
    report_batch_workers: int = 2
    report_generation_batch_max_tokens: Mapping[ReportModel, int] = field(
        default_factory=lambda: _model_limits()[0]
    )
    report_generation_context_tokens: Mapping[ReportModel, int] = field(
        default_factory=_default_context
    )
    report_generation_default_effort: Mapping[ReportModel, ReportEffort] = field(
        default_factory=_default_effort
    )
    xai_model: str = REPORT_MODELS["grok-4.3"].model
    xai_api_base: str = "https://api.x.ai/v1"
    ai_provider: str = "ollama"
    hf_model: str = REPORT_MODELS["huggingface-deepseek-v4-flash"].model
    hf_api_base: str = "https://router.huggingface.co/v1"
    ollama_model: str = REPORT_MODELS[DEFAULT_REPORT_MODEL].model
    ollama_api_base: str = "http://localhost:11434/v1"
    ollama_keep_alive_seconds: int = 60
    ollama_max_output_tokens_by_model: Mapping[ReportModel, int] = field(
        default_factory=lambda: _ollama_output_limits(None)
    )
    deepseek_model: str = REPORT_MODELS["deepseek-flash"].model
    deepseek_api_base: str = "https://api.deepseek.com"
    vllm_model: str = REPORT_MODELS["vllm-qwen3.5:4b"].model
    vllm_api_base: str = "http://localhost:8001/v1"
    # Identification of a condition the dictionary does not know (ai/condition_ai.py):
    # Identification uses only the host Ollama model, with no provider fallback.
    medical_condition_ai_local_model: str = "gemma3:1b"
    condition_ai_local_base: str = "http://localhost:11434/v1"
    condition_ai_timeout_seconds: int = 10
    condition_ai_max_output_tokens: int = 300
    herb_association_ai_base: str = "http://localhost:11434/v1"
    herb_association_ai_model: str = "qwen3.5:9b"
    herb_association_ai_max_units: int = 6
    herb_association_ai_max_pairs: int = 20
    herb_association_ai_max_input_chars: int = 200000
    herb_association_ai_max_passage_chars: int = 1000
    herb_association_ai_context_tokens: int = 32768
    herb_association_ai_max_output_tokens: int = 2048
    herb_association_ai_timeout_seconds: int = 900
    herb_association_ai_keep_alive_seconds: int = 3600
    herb_association_build_timeout_seconds: int = 7200
    herb_association_ai_max_requests: int = 1000
    herb_safety_ai_max_requests: int = 10000
    herb_safety_ai_context_tokens: int = 65536
    herb_safety_ai_max_output_tokens: int = 40000
    herb_safety_build_timeout_seconds: int = 86400
    herb_safety_ministral_batch_size: int = 10
    herb_safety_deepseek_batch_size: int = 100
    herb_safety_deepseek_max_output_tokens: int = 160000
    # Local model that groups equivalent messages; chosen by comparing three local models.
    herb_safety_dedup_model: str = "gemma4:12b"
    # Local model of the generation stage (stage id `ministral`); empty
    # disables the local stage so only DeepSeek generates.
    herb_safety_generation_model: str = "ministral-3:8b"
    # Empty keeps the single-product monolingual flow; see parse_safety_scope.
    herb_safety_extension_products: str = ""
    # Orders "top N <category> for <condition>"; see core/score_formula.py for the grammar.
    herb_condition_top_formula: str = DEFAULT_FORMULA
    message_classification_timeout_seconds: int = 10
    message_classification_max_output_tokens: int = 300
    ai_stream: bool = False
    ai_max_output_tokens: int = 20000
    ai_read_timeout_seconds: int = 300
    session_idle_seconds: int = 3600
    session_max_seconds: int = 14400
    max_chat_chars: int = 4000
    max_requests_per_minute: int = 60
    log_level: str = "INFO"
    log_fragment_text: bool = False
    log_fragment_text_max_chars: int = 4000
    log_ai_response_text: bool = False

    max_active_sessions: int = 100
    new_sessions_per_ip_minute: int = 10
    new_sessions_per_cookie_minute: int = 5
    max_history_bytes: int = 8388608
    max_evidence_bytes: int = 25165824
    max_pdf_bytes: int = 16777216
    max_session_bytes: int = 67108864
    max_global_bytes: int = 268435456
    max_api_body_bytes: int = 262144
    owner_login_per_minute: int = 5
    max_concurrent_searches: int = 2
    max_concurrent_generations: int = 1
    max_queued_generations: int = 20
    operation_timeout_seconds: int = 600
    report_generation_timeout_seconds: int = 600
    report_shutdown_timeout_seconds: int = 20
    session_reconnect_grace_seconds: int = 30
    operation_reservation_bytes: int = 65536
    owner_key: str = field(default="", repr=False)
    cookie_secure: bool = False
    public_root_path: str = ""
    public_origin: str = ""
    deployment_profile: str = "local"
    # from_env snapshots secrets; direct legacy constructors can still use the
    # environment when their optional credential is not supplied.
    xai_key: str | None = field(default=None, repr=False)
    hf_api_token: str | None = field(default=None, repr=False)
    deepseek_key: str | None = field(default=None, repr=False)
    ollama_key: str | None = field(default=None, repr=False)

    @property
    def report_generation_model(self) -> ReportModel:
        return self.report_generation_models[0]

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None, *, dotenv: bool = False) -> "Settings":
        """Read configuration explicitly; tests pass a mapping and never load .env."""
        if dotenv:
            if env is not None:
                raise ValueError("dotenv cannot be combined with an injected environment")
            load_dotenv(ROOT / ".env", override=False)
        env = os.environ if env is None else env
        for old, new in (
            (
                "REPORT_GENERATION_BATCH_MAX_CHARS_BY_MODEL",
                "REPORT_GENERATION_BATCH_MAX_TOKENS_BY_MODEL",
            ),
        ):
            if env.get(old, "").strip():
                raise ValueError(f"{old} was replaced by {new}; configure token budgets explicitly")
        report_models = parse_report_models(
            env.get("REPORT_GENERATION_MODELS", ",".join(DEFAULT_REPORT_MODELS))
        )
        report_model = report_models[0]
        report_spec = REPORT_MODELS[report_model]
        model_limits = _model_limits(env.get(ENV_NAME))
        return cls(
            documents_dir=Path(env.get("DOCUMENTS_DIR", str(CORPUS_DATA_DIR / "documents" / "ro"))),
            documents_en_dir=Path(
                env.get("DOCUMENTS_EN_DIR", str(CORPUS_DATA_DIR / "documents" / "en"))
            ),
            herb_images_dir=Path(env.get("HERB_IMAGES_DIR", str(CORPUS_DATA_DIR / "images"))),
            model_cache_dir=Path(env.get("MODEL_CACHE_DIR", str(ROOT / "model_cache"))),
            embedding_threads=_int("EMBEDDING_THREADS", min(8, os.cpu_count() or 8), env=env),
            embedding_device=_embedding_device(env=env),
            frontend_dist_dir=Path(
                env.get("FRONTEND_DIST_DIR", str(ROOT / "src" / "frontend" / "dist"))
            ),
            database_url=env.get(
                "DATABASE_URL", "postgresql://medicina:medicina@127.0.0.1:5432/medicina"
            ),
            database_bootstrap_url=env.get("DATABASE_BOOTSTRAP_URL", ""),
            temp_dir=Path(
                env.get(
                    "SESSION_TEMP_DIR",
                    "/tmp/naturist-sessions" if os.name != "nt" else str(ROOT / "var" / "sessions"),
                )
            ),
            report_generation_models=report_models,
            report_batch_workers=_int("REPORT_BATCH_WORKERS", 2, env=env),
            report_generation_batch_max_tokens=model_limits[0],
            report_generation_context_tokens=model_limits[1],
            report_generation_default_effort=model_limits[2],
            xai_api_base=env.get("XAI_API_BASE", "https://api.x.ai/v1").rstrip("/"),
            ai_provider=report_spec.provider,
            hf_api_base=env.get("HF_API_BASE", "https://router.huggingface.co/v1").rstrip("/"),
            ollama_model=report_spec.model
            if report_spec.provider == "ollama"
            else REPORT_MODELS[DEFAULT_REPORT_MODEL].model,
            ollama_api_base=env.get("OLLAMA_API_BASE", "http://localhost:11434/v1").rstrip("/"),
            ollama_keep_alive_seconds=_int("OLLAMA_KEEP_ALIVE_SECONDS", 60, minimum=0, env=env),
            ollama_max_output_tokens_by_model=_ollama_output_limits(
                env.get("OLLAMA_MAX_OUTPUT_TOKENS_BY_MODEL")
            ),
            deepseek_api_base=env.get("DEEPSEEK_API_BASE", "https://api.deepseek.com").rstrip("/"),
            vllm_model=report_spec.model
            if report_spec.provider == "vllm"
            else REPORT_MODELS["vllm-qwen3.5:4b"].model,
            vllm_api_base=env.get("VLLM_API_BASE", "http://localhost:8001/v1").rstrip("/"),
            medical_condition_ai_local_model=env.get(
                "MEDICAL_CONDITION_AI_LOCAL_MODEL", "gemma3:1b"
            ),
            condition_ai_local_base=env.get(
                "CONDITION_AI_LOCAL_BASE", "http://localhost:11434/v1"
            ).rstrip("/"),
            condition_ai_timeout_seconds=_int("CONDITION_AI_TIMEOUT_SECONDS", 10, env=env),
            condition_ai_max_output_tokens=_int("CONDITION_AI_MAX_OUTPUT_TOKENS", 300, env=env),
            herb_association_ai_base=env.get(
                "HERB_ASSOCIATION_AI_BASE",
                env.get("CONDITION_AI_LOCAL_BASE", "http://localhost:11434/v1"),
            ).rstrip("/"),
            herb_association_ai_model=env.get("HERB_ASSOCIATION_AI_MODEL", "qwen3.5:9b"),
            herb_association_ai_max_units=_int("HERB_ASSOCIATION_AI_MAX_UNITS", 6, env=env),
            herb_association_ai_max_pairs=_int("HERB_ASSOCIATION_AI_MAX_PAIRS", 20, env=env),
            herb_association_ai_max_input_chars=_int(
                "HERB_ASSOCIATION_AI_MAX_INPUT_CHARS", 100000, env=env
            ),
            herb_association_ai_max_passage_chars=_int(
                "HERB_ASSOCIATION_AI_MAX_PASSAGE_CHARS", 1000, env=env
            ),
            herb_association_ai_context_tokens=_int(
                "HERB_ASSOCIATION_AI_CONTEXT_TOKENS", 32768, env=env
            ),
            herb_association_ai_max_output_tokens=_int(
                "HERB_ASSOCIATION_AI_MAX_OUTPUT_TOKENS", 2048, env=env
            ),
            herb_association_ai_timeout_seconds=_int(
                "HERB_ASSOCIATION_AI_TIMEOUT_SECONDS", 900, env=env
            ),
            herb_association_ai_keep_alive_seconds=_int(
                "HERB_ASSOCIATION_AI_KEEP_ALIVE_SECONDS", 3600, minimum=-1, env=env
            ),
            herb_association_build_timeout_seconds=_int(
                "HERB_ASSOCIATION_BUILD_TIMEOUT_SECONDS", 7200, env=env
            ),
            herb_association_ai_max_requests=_int(
                "HERB_ASSOCIATION_AI_MAX_REQUESTS", 1000, env=env
            ),
            herb_safety_ai_max_requests=_int("HERB_SAFETY_AI_MAX_REQUESTS", 10000, env=env),
            herb_safety_ai_context_tokens=_int("HERB_SAFETY_AI_CONTEXT_TOKENS", 65536, env=env),
            herb_safety_ai_max_output_tokens=_int(
                "HERB_SAFETY_AI_MAX_OUTPUT_TOKENS", 40000, env=env
            ),
            herb_safety_build_timeout_seconds=_int(
                "HERB_SAFETY_BUILD_TIMEOUT_SECONDS", 86400, env=env
            ),
            herb_safety_ministral_batch_size=_int("HERB_SAFETY_MINISTRAL_BATCH_SIZE", 10, env=env),
            herb_safety_deepseek_batch_size=_int("HERB_SAFETY_DEEPSEEK_BATCH_SIZE", 100, env=env),
            herb_safety_deepseek_max_output_tokens=_int(
                "HERB_SAFETY_DEEPSEEK_MAX_OUTPUT_TOKENS", 160000, env=env
            ),
            herb_safety_dedup_model=env.get("HERB_SAFETY_DEDUP_MODEL", "gemma4:12b").strip(),
            herb_safety_generation_model=env.get(
                "HERB_SAFETY_GENERATION_MODEL", "ministral-3:8b"
            ).strip(),
            herb_safety_extension_products=env.get("HERB_SAFETY_EXTENSION_PRODUCTS", "").strip(),
            herb_condition_top_formula=env.get(
                "HERB_CONDITION_TOP_FORMULA", DEFAULT_FORMULA
            ).strip(),
            message_classification_timeout_seconds=_int(
                "MESSAGE_CLASSIFICATION_TIMEOUT_SECONDS", 10, env=env
            ),
            message_classification_max_output_tokens=_int(
                "MESSAGE_CLASSIFICATION_MAX_OUTPUT_TOKENS", 300, env=env
            ),
            ai_stream=_bool("REPORT_GENERATION_AI_STREAM", False, env=env),
            ai_max_output_tokens=_int("REPORT_GENERATION_MAX_OUTPUT_TOKENS", 20000, env=env),
            ai_read_timeout_seconds=_int("REPORT_GENERATION_READ_TIMEOUT_SECONDS", 300, env=env),
            session_idle_seconds=_int("SESSION_IDLE_SECONDS", 3600, env=env),
            session_max_seconds=_int("SESSION_MAX_SECONDS", 14400, env=env),
            max_chat_chars=_int("MAX_CHAT_CHARS", 4000, env=env),
            max_requests_per_minute=_int("MAX_REQUESTS_PER_MINUTE", 60, env=env),
            log_level=env.get("LOG_LEVEL", "INFO").strip().upper(),
            log_fragment_text=_bool("LOG_FRAGMENT_TEXT", False, env=env),
            log_fragment_text_max_chars=_int("LOG_FRAGMENT_TEXT_MAX_CHARS", 4000, env=env),
            log_ai_response_text=_bool("LOG_AI_RESPONSE_TEXT", False, env=env),
            max_active_sessions=_int("MAX_ACTIVE_SESSIONS", 100, env=env),
            new_sessions_per_ip_minute=_int("NEW_SESSIONS_PER_IP_MINUTE", 10, env=env),
            new_sessions_per_cookie_minute=_int("NEW_SESSIONS_PER_COOKIE_MINUTE", 5, env=env),
            max_history_bytes=_int("MAX_HISTORY_BYTES", 8388608, env=env),
            max_evidence_bytes=_int("MAX_EVIDENCE_BYTES", 25165824, env=env),
            max_pdf_bytes=_int("MAX_PDF_BYTES", 16777216, env=env),
            max_session_bytes=_int("MAX_SESSION_BYTES", 67108864, env=env),
            max_global_bytes=_int("MAX_GLOBAL_BYTES", 268435456, env=env),
            max_api_body_bytes=_int("MAX_API_BODY_BYTES", 262144, env=env),
            owner_login_per_minute=_int("OWNER_LOGIN_PER_MINUTE", 5, env=env),
            max_concurrent_searches=_int("MAX_CONCURRENT_SEARCHES", 2, env=env),
            max_concurrent_generations=_int("MAX_CONCURRENT_GENERATIONS", 1, env=env),
            max_queued_generations=_int("MAX_QUEUED_GENERATIONS", 20, env=env),
            operation_timeout_seconds=_int("OPERATION_TIMEOUT_SECONDS", 600, env=env),
            report_generation_timeout_seconds=_int(
                "REPORT_GENERATION_TIMEOUT_SECONDS", 600, env=env
            ),
            report_shutdown_timeout_seconds=_int("REPORT_SHUTDOWN_TIMEOUT_SECONDS", 20, env=env),
            session_reconnect_grace_seconds=_int("SESSION_RECONNECT_GRACE_SECONDS", 30, env=env),
            operation_reservation_bytes=_int("OPERATION_RESERVATION_BYTES", 65536, env=env),
            owner_key=env.get("OWNER_KEY", ""),
            cookie_secure=_bool("COOKIE_SECURE", False, env=env),
            public_root_path=env.get("PUBLIC_ROOT_PATH", env.get("GRADIO_ROOT_PATH", "")).rstrip(
                "/"
            ),
            public_origin=env.get("PUBLIC_ORIGIN", "").strip().rstrip("/"),
            deployment_profile=env.get("DEPLOYMENT_PROFILE", "local").strip().lower(),
            xai_key=env.get("X_API_KEY", "").strip(),
            hf_api_token=env.get("HF_TOKEN", "").strip(),
            deepseek_key=env.get("DEEPSEEK_API_KEY", "").strip(),
            ollama_key=env.get("OLLAMA_API_KEY", "").strip(),
        )

    # Reject an unknown provider even when Settings is built directly (tests).
    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "report_generation_models",
            parse_report_models(",".join(self.report_generation_models)),
        )
        limits = self.report_generation_batch_max_tokens
        if (
            not isinstance(limits, Mapping)
            or set(limits) - set(REPORT_MODELS)
            or any(type(value) is not int or value <= 0 for value in limits.values())
        ):
            raise ValueError("Report batch limits must map supported models to positive integers")
        if set(self.report_generation_models) - set(limits):
            raise ValueError("Report batch limits must include every configured model")
        object.__setattr__(
            self, "report_generation_batch_max_tokens", MappingProxyType(dict(limits))
        )
        contexts = self.report_generation_context_tokens
        efforts = self.report_generation_default_effort
        if (
            not isinstance(contexts, Mapping)
            or set(contexts) != set(REPORT_MODELS)
            or any(type(value) is not int or value <= 0 for value in contexts.values())
        ):
            raise ValueError(
                "Report model contexts must map every supported model to a positive integer"
            )
        if (
            not isinstance(efforts, Mapping)
            or set(efforts) != set(REPORT_MODELS)
            or any(value not in REPORT_EFFORTS for value in efforts.values())
        ):
            raise ValueError("Report model efforts must map every supported model to an effort")
        for model, spec in REPORT_MODELS.items():
            if spec.context_tokens is not None and contexts[model] != spec.context_tokens:
                raise ValueError(f"The context of {model} is fixed at {spec.context_tokens} tokens")
        object.__setattr__(
            self, "report_generation_context_tokens", MappingProxyType(dict(contexts))
        )
        object.__setattr__(
            self, "report_generation_default_effort", MappingProxyType(dict(efforts))
        )
        _ai_provider(self.ai_provider)
        outputs = _freeze_ollama_output_limits(self.ollama_max_output_tokens_by_model)
        for model, spec in REPORT_MODELS.items():
            if (
                spec.provider == "ollama"
                and spec.context_tokens is not None
                and outputs.get(model, self.ai_max_output_tokens) >= spec.context_tokens
            ):
                raise ValueError("Ollama output token limit must be smaller than its context")
        object.__setattr__(self, "ollama_max_output_tokens_by_model", outputs)
        # Every active model must keep room for its input after the default output.
        for model in self.report_generation_models:
            output = (
                outputs.get(model, self.ai_max_output_tokens)
                if REPORT_MODELS[model].provider == "ollama"
                else self.ai_max_output_tokens
            )
            if contexts[model] - output < MIN_REPORT_INPUT_TOKENS:
                raise ValueError(
                    f"The output token limit of {model} ({output}) leaves fewer than "
                    f"{MIN_REPORT_INPUT_TOKENS} input tokens in its context ({contexts[model]})"
                )
        for name in ("ai_stream", "log_fragment_text", "log_ai_response_text", "cookie_secure"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be boolean")
        if self.embedding_device not in EMBEDDING_DEVICES:
            raise ValueError("embedding_device must be cpu or cuda")
        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("log_level must be a supported logging level")
        if self.deployment_profile not in {"local", "public"}:
            raise ValueError("deployment_profile must be local or public")
        for name in (
            "xai_api_base",
            "hf_api_base",
            "ollama_api_base",
            "deepseek_api_base",
            "vllm_api_base",
            "condition_ai_local_base",
            "herb_association_ai_base",
        ):
            try:
                parsed = urlsplit(getattr(self, name))
                valid = (
                    parsed.scheme in {"http", "https"}
                    and bool(parsed.hostname)
                    and not parsed.username
                    and not parsed.password
                    and not parsed.query
                    and not parsed.fragment
                    and not any(c.isspace() for c in getattr(self, name))
                )
                if parsed.port is not None and parsed.port < 1:
                    valid = False
            except ValueError:
                valid = False
            if not valid:
                raise ValueError(f"{name} must be an HTTP(S) URL without credentials")
        association_base = urlsplit(self.herb_association_ai_base)
        if association_base.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
            "host.docker.internal",
        } or association_base.path not in {"", "/v1"}:
            raise ValueError("herb_association_ai_base must point to local Ollama")
        if not self.herb_association_ai_model.strip() or any(
            c.isspace() for c in self.herb_association_ai_model
        ):
            raise ValueError("herb_association_ai_model must be an explicit model tag")
        for name in (
            "herb_association_ai_max_units",
            "herb_association_ai_max_pairs",
            "herb_association_ai_max_input_chars",
            "herb_association_ai_max_passage_chars",
            "herb_association_ai_context_tokens",
            "herb_association_ai_max_output_tokens",
            "herb_association_ai_timeout_seconds",
            "herb_association_build_timeout_seconds",
            "herb_association_ai_max_requests",
            "herb_safety_ai_max_requests",
            "herb_safety_ai_context_tokens",
            "herb_safety_ai_max_output_tokens",
            "herb_safety_build_timeout_seconds",
            "herb_safety_ministral_batch_size",
            "herb_safety_deepseek_batch_size",
            "herb_safety_deepseek_max_output_tokens",
        ):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if not self.herb_safety_dedup_model or any(
            c.isspace() for c in self.herb_safety_dedup_model
        ):
            raise ValueError("herb_safety_dedup_model must be an explicit model tag")
        if any(c.isspace() for c in self.herb_safety_generation_model):
            raise ValueError("herb_safety_generation_model must be empty or a model tag")
        compile_formula(self.herb_condition_top_formula)
        if not isinstance(self.herb_safety_extension_products, str):
            raise ValueError("herb_safety_extension_products must be a string")
        # Batch sizes matter only while the bilingual extension is active, so the single-product
        # flow keeps working with any output limit it already accepted.
        if parse_safety_scope(self.herb_safety_extension_products).mode != "off":
            if (
                safety_output_estimate(self.herb_safety_ministral_batch_size)
                > self.herb_safety_ai_max_output_tokens
            ):
                raise ValueError("herb safety ministral batch does not fit the output token limit")
            if (
                safety_output_estimate(self.herb_safety_deepseek_batch_size)
                > self.herb_safety_deepseek_max_output_tokens
            ):
                raise ValueError("herb safety deepseek batch does not fit the output token limit")
        if self.herb_association_ai_max_units > 6:
            raise ValueError("herb_association_ai_max_units must not exceed 6 source passages")
        if (
            type(self.herb_association_ai_keep_alive_seconds) is not int
            or self.herb_association_ai_keep_alive_seconds < -1
        ):
            raise ValueError("herb_association_ai_keep_alive_seconds must be -1 or non-negative")
        if self.herb_association_ai_max_passage_chars > 1000:
            raise ValueError("herb_association_ai_max_passage_chars must not exceed 1000")
        if (
            self.herb_association_ai_max_output_tokens + 512
            >= self.herb_association_ai_context_tokens
        ):
            raise ValueError("herb association output must leave context for input")
        if self.herb_association_ai_timeout_seconds > self.herb_association_build_timeout_seconds:
            raise ValueError("herb association request timeout must fit build timeout")
        if self.herb_safety_ai_max_output_tokens + 512 >= self.herb_safety_ai_context_tokens:
            raise ValueError("herb safety output must fit its dedicated context")
        if self.herb_association_ai_timeout_seconds > self.herb_safety_build_timeout_seconds:
            raise ValueError("herb safety request timeout must fit build timeout")
        database = urlsplit(self.database_url)
        if (
            database.scheme not in {"postgresql", "postgres"}
            or not database.hostname
            or not database.path.strip("/")
        ):
            raise ValueError("database_url must name a PostgreSQL host and database")
        try:
            database.port
        except ValueError:
            raise ValueError("database_url has an invalid port") from None
        for name in (
            "documents_dir",
            "documents_en_dir",
            "herb_images_dir",
            "model_cache_dir",
            "frontend_dist_dir",
            "temp_dir",
        ):
            if "\x00" in str(getattr(self, name)):
                raise ValueError(f"{name} contains an invalid path character")
        object.__setattr__(self, "public_root_path", self.public_root_path.rstrip("/"))
        if self.public_origin:
            try:
                origin = urlsplit(self.public_origin)
                valid_origin = (
                    origin.scheme in {"http", "https"}
                    and bool(origin.hostname)
                    and not origin.username
                    and not origin.password
                    and origin.path in {"", "/"}
                    and not origin.query
                    and not origin.fragment
                    and not any(character.isspace() for character in self.public_origin)
                )
                # Accessing port rejects malformed/out-of-range values.
                if origin.port is not None and origin.port < 1:
                    valid_origin = False
            except ValueError:
                valid_origin = False
            if not valid_origin:
                raise ValueError(
                    "public_origin must be an HTTP(S) origin without a path or credentials"
                )
        if type(self.ollama_keep_alive_seconds) is not int or self.ollama_keep_alive_seconds < 0:
            raise ValueError("ollama_keep_alive_seconds must be non-negative")
        if type(self.report_batch_workers) is not int or self.report_batch_workers <= 0:
            raise ValueError("report_batch_workers must be a positive integer")
        for name in (
            "embedding_threads",
            "condition_ai_timeout_seconds",
            "condition_ai_max_output_tokens",
            "message_classification_timeout_seconds",
            "message_classification_max_output_tokens",
            "ai_max_output_tokens",
            "ai_read_timeout_seconds",
            "log_fragment_text_max_chars",
            "session_idle_seconds",
            "session_max_seconds",
            "max_requests_per_minute",
            "max_chat_chars",
            "max_active_sessions",
            "new_sessions_per_ip_minute",
            "new_sessions_per_cookie_minute",
            "max_history_bytes",
            "max_evidence_bytes",
            "max_pdf_bytes",
            "max_session_bytes",
            "max_global_bytes",
            "max_api_body_bytes",
            "owner_login_per_minute",
            "max_concurrent_searches",
            "max_concurrent_generations",
            "max_queued_generations",
            "operation_timeout_seconds",
            "report_generation_timeout_seconds",
            "report_shutdown_timeout_seconds",
            "session_reconnect_grace_seconds",
            "operation_reservation_bytes",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.session_idle_seconds > self.session_max_seconds:
            raise ValueError("session_idle_seconds must not exceed session_max_seconds")
        if self.max_concurrent_generations != 1:
            raise ValueError("max_concurrent_generations must be 1 for the serial report queue")
        if (
            max(self.max_history_bytes, self.max_evidence_bytes, self.max_pdf_bytes)
            > self.max_session_bytes
        ):
            raise ValueError("component budgets must not exceed max_session_bytes")
        if self.max_session_bytes > self.max_global_bytes:
            raise ValueError("max_session_bytes must not exceed max_global_bytes")
        if self.operation_reservation_bytes > self.max_session_bytes:
            raise ValueError("operation reservation must fit the session budget")
        if self.public_root_path and (
            not self.public_root_path.startswith("/")
            or self.public_root_path.startswith("//")
            or any(c in self.public_root_path for c in "?#\\")
            or ".." in self.public_root_path
            or not all(c.isalnum() or c in "/_-" for c in self.public_root_path)
        ):
            raise ValueError("public_root_path must be a safe absolute URL path")
        if self.deployment_profile == "public":
            if not self.public_origin.startswith("https://") or not self.cookie_secure:
                raise ValueError("public deployment requires an HTTPS origin and Secure cookies")
            if self.log_fragment_text or self.log_ai_response_text:
                raise ValueError("public deployment forbids content logging")

    # Return the configured xAI API key without surrounding whitespace.
    def api_key(self) -> str:
        return (os.getenv("X_API_KEY", "") if self.xai_key is None else self.xai_key).strip()

    # Return the Hugging Face Inference Providers token without surrounding whitespace.
    def hf_token(self) -> str:
        return (
            os.getenv("HF_TOKEN", "") if self.hf_api_token is None else self.hf_api_token
        ).strip()

    # Return the DeepSeek API key without surrounding whitespace.
    def deepseek_api_key(self) -> str:
        return (
            os.getenv("DEEPSEEK_API_KEY", "") if self.deepseek_key is None else self.deepseek_key
        ).strip()

    # Return the Ollama Cloud API key without surrounding whitespace.
    def ollama_api_key(self) -> str:
        return (
            os.getenv("OLLAMA_API_KEY", "") if self.ollama_key is None else self.ollama_key
        ).strip()


settings = Settings()


def configure_settings(value: Settings) -> None:
    """Configure legacy retrieval modules explicitly at runtime, before workers start."""
    from dataclasses import fields

    from backend.ai.condition_repository import clear_catalog_cache
    from backend.ai.herb_repository import clear_herb_catalog_cache

    clear_catalog_cache()
    clear_herb_catalog_cache()

    for item in fields(Settings):
        object.__setattr__(settings, item.name, getattr(value, item.name))
