"""Environment-backed settings. No patient data belongs in configuration or logs."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DATA_DIR = ROOT / "medicina-naturista-documente" / "data"
load_dotenv(ROOT / ".env", override=False)


# Read an integer setting and reject values outside its safety bounds.
def _int(name: str, default: int, minimum: int = 1, maximum: int | None = None) -> int:
    value = int(os.getenv(name, str(default)))
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return value


# Parse a human-friendly boolean environment variable with strict validation.
def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


EMBEDDING_DEVICES = ("cpu", "cuda")


# Read EMBEDDING_DEVICE and reject anything that is not a known device.
def _embedding_device() -> str:
    device = os.getenv("EMBEDDING_DEVICE", "cpu").strip().casefold()
    if device not in EMBEDDING_DEVICES:
        raise ValueError(f"EMBEDDING_DEVICE must be one of {', '.join(EMBEDDING_DEVICES)}")
    return device


AI_PROVIDERS = ("xai", "huggingface", "ollama", "deepseek")


# Read AI_PROVIDER and reject anything that is not a known provider.
def _ai_provider(value: str | None = None) -> str:
    provider = (os.getenv("AI_PROVIDER", "xai") if value is None else value).strip().casefold()
    if provider not in AI_PROVIDERS:
        raise ValueError(f"AI_PROVIDER must be one of {', '.join(AI_PROVIDERS)}")
    return provider


CONDITION_AI_BACKEND_NAMES = ("huggingface", "local")


# Read CONDITION_AI_BACKENDS: an ordered, comma-separated list of the backends
# that identify a condition the dictionary does not know. Empty disables the step.
def _condition_ai_backends() -> tuple[str, ...]:
    raw = os.getenv("CONDITION_AI_BACKENDS", "local,huggingface")
    names = tuple(dict.fromkeys(part.strip().casefold() for part in raw.split(",") if part.strip()))
    unknown = [name for name in names if name not in CONDITION_AI_BACKEND_NAMES]
    if unknown:
        raise ValueError(f"CONDITION_AI_BACKENDS must only contain {', '.join(CONDITION_AI_BACKEND_NAMES)}")
    return names


@dataclass(frozen=True)
class Settings:
    documents_dir: Path = Path(os.getenv("DOCUMENTS_DIR", str(CORPUS_DATA_DIR / "documents")))
    model_cache_dir: Path = Path(os.getenv("MODEL_CACHE_DIR", str(ROOT / "model_cache")))
    # Threads of the ONNX embedding model. Few threads beat all cores on hybrid
    # (P/E-core) CPUs, so the default is 8, capped at the machine's core count.
    embedding_threads: int = _int("EMBEDDING_THREADS", min(8, os.cpu_count() or 8))
    # Device of the index build's embedding model: "cpu" (FastEmbed) or "cuda"
    # (PyTorch fp16, needs the GPU environment). Queries always run on the CPU.
    embedding_device: str = _embedding_device()
    conditions_file: Path = Path(os.getenv("CONDITIONS_FILE", str(CORPUS_DATA_DIR / "medical_conditions.jsonl")))
    herbs_file: Path = Path(os.getenv("HERBS_FILE", str(CORPUS_DATA_DIR / "herbs.jsonl")))
    frontend_dist_dir: Path = Path(os.getenv("FRONTEND_DIST_DIR", str(ROOT / "src" / "frontend" / "dist")))
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql://medicina:medicina@127.0.0.1:5432/medicina"
    )
    temp_dir: Path = Path(os.getenv("SESSION_TEMP_DIR", "/tmp/naturist-sessions" if os.name != "nt" else str(ROOT / "var" / "sessions")))
    xai_model: str = os.getenv("XAI_MODEL", "grok-4.3")
    xai_reasoning_effort: str = os.getenv("XAI_REASONING_EFFORT", "medium")
    xai_max_context_chars: int = _int("X_AI_MAX_CONTEXT_CHARS", 1_000_000)
    xai_api_base: str = os.getenv("XAI_API_BASE", "https://api.x.ai/v1").rstrip("/")
    ai_provider: str = _ai_provider()
    hf_model: str = os.getenv("HF_MODEL", "deepseek-ai/DeepSeek-V4-Flash:deepinfra")
    hf_api_base: str = os.getenv("HF_API_BASE", "https://router.huggingface.co/v1").rstrip("/")
    hf_reasoning_effort: str = os.getenv("HF_REASONING_EFFORT", "").strip()
    hf_max_context_chars: int = _int("HF_MAX_CONTEXT_CHARS", 120_000)
    ollama_model: str = os.getenv("OLLAMA_MODEL", "deepseek-v4.1-flash:cloud")
    ollama_api_base: str = os.getenv("OLLAMA_API_BASE", "http://localhost:11434/v1").rstrip("/")
    ollama_reasoning_effort: str = os.getenv("OLLAMA_REASONING_EFFORT", "").strip()
    ollama_max_context_chars: int = _int("OLLAMA_MAX_CONTEXT_CHARS", 1_000_000)
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
    deepseek_api_base: str = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com").rstrip("/")
    deepseek_reasoning_effort: str = os.getenv("DEEPSEEK_REASONING_EFFORT", "").strip()
    deepseek_max_context_chars: int = _int("DEEPSEEK_MAX_CONTEXT_CHARS", 1_000_000)
    # Identification of a condition the dictionary does not know (ai/condition_ai.py):
    # backends are tried in order; the local one is an Ollama model, the other
    # goes through the Hugging Face router (HF_API_BASE, HF_TOKEN).
    condition_ai_backends: tuple[str, ...] = _condition_ai_backends()
    condition_ai_hf_model: str = os.getenv(
        "CONDITION_AI_HF_MODEL", os.getenv("HF_MODEL", "deepseek-ai/DeepSeek-V4-Flash:deepinfra")
    )
    condition_ai_local_model: str = os.getenv("CONDITION_AI_LOCAL_MODEL", "gemma3:1b")
    condition_ai_local_base: str = os.getenv("CONDITION_AI_LOCAL_BASE", "http://localhost:11434/v1").rstrip("/")
    condition_ai_timeout_seconds: int = _int("CONDITION_AI_TIMEOUT_SECONDS", 10)
    condition_ai_max_output_tokens: int = _int("CONDITION_AI_MAX_OUTPUT_TOKENS", 300)
    ai_stream: bool = _bool("AI_STREAM", False)
    ai_max_output_tokens: int = _int("AI_MAX_OUTPUT_TOKENS", 20000)
    ai_read_timeout_seconds: int = _int("AI_READ_TIMEOUT_SECONDS", 300)
    session_idle_seconds: int = _int("SESSION_IDLE_SECONDS", 3600)
    session_max_seconds: int = _int("SESSION_MAX_SECONDS", 14400)
    max_chat_chars: int = _int("MAX_CHAT_CHARS", 4000)
    max_requests_per_minute: int = _int("MAX_REQUESTS_PER_MINUTE", 60)
    log_level: str = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    log_fragment_text: bool = _bool("LOG_FRAGMENT_TEXT", True)
    log_fragment_text_max_chars: int = _int("LOG_FRAGMENT_TEXT_MAX_CHARS", 4000)
    log_ai_response_text: bool = _bool("LOG_AI_RESPONSE_TEXT", False)

    # Reject an unknown provider even when Settings is built directly (tests).
    def __post_init__(self) -> None:
        _ai_provider(self.ai_provider)

    # Return the configured xAI API key without surrounding whitespace.
    def api_key(self) -> str:
        return os.getenv("X_API_KEY", "").strip()

    # Return the Hugging Face Inference Providers token without surrounding whitespace.
    def hf_token(self) -> str:
        return os.getenv("HF_TOKEN", "").strip()

    # Return the DeepSeek API key without surrounding whitespace.
    def deepseek_api_key(self) -> str:
        return os.getenv("DEEPSEEK_API_KEY", "").strip()

    # Return the Ollama Cloud API key without surrounding whitespace.
    def ollama_api_key(self) -> str:
        return os.getenv("OLLAMA_API_KEY", "").strip()


settings = Settings()
