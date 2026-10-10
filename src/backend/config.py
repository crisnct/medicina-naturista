"""Environment-backed settings. No patient data belongs in configuration or logs."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DATA_DIR = ROOT / "medicina-naturista-documente" / "data"


# Read an integer setting and reject values outside its safety bounds.
def _int(
    name: str, default: int, minimum: int = 1, maximum: int | None = None, env=None
) -> int:
    value = int((env or {}).get(name, str(default)))
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return value


# Parse a human-friendly boolean environment variable with strict validation.
def _bool(name: str, default: bool, env=None) -> bool:
    value = (env or {}).get(name)
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
def _embedding_device(env=None) -> str:
    device = (env or {}).get("EMBEDDING_DEVICE", "cpu").strip().casefold()
    if device not in EMBEDDING_DEVICES:
        raise ValueError(
            f"EMBEDDING_DEVICE must be one of {', '.join(EMBEDDING_DEVICES)}"
        )
    return device


AI_PROVIDERS = ("xai", "huggingface", "ollama", "deepseek")


# Read AI_PROVIDER and reject anything that is not a known provider.
def _ai_provider(value: str | None = None, env=None) -> str:
    provider = (
        ((env or {}).get("AI_PROVIDER", "xai") if value is None else value)
        .strip()
        .casefold()
    )
    if provider not in AI_PROVIDERS:
        raise ValueError(f"AI_PROVIDER must be one of {', '.join(AI_PROVIDERS)}")
    return provider


CONDITION_AI_BACKEND_NAMES = ("huggingface", "local")


# Read CONDITION_AI_BACKENDS: an ordered, comma-separated list of the backends
# that identify a condition the dictionary does not know. Empty disables the step.
def _condition_ai_backends(env=None) -> tuple[str, ...]:
    raw = (env or {}).get("CONDITION_AI_BACKENDS", "local,huggingface")
    names = tuple(
        dict.fromkeys(
            part.strip().casefold() for part in raw.split(",") if part.strip()
        )
    )
    unknown = [name for name in names if name not in CONDITION_AI_BACKEND_NAMES]
    if unknown:
        raise ValueError(
            f"CONDITION_AI_BACKENDS must only contain {', '.join(CONDITION_AI_BACKEND_NAMES)}"
        )
    return names


@dataclass(frozen=True)
class Settings:
    documents_dir: Path = CORPUS_DATA_DIR / "documents"
    model_cache_dir: Path = ROOT / "model_cache"
    # Threads of the ONNX embedding model. Few threads beat all cores on hybrid
    # (P/E-core) CPUs, so the default is 8, capped at the machine's core count.
    embedding_threads: int = min(8, os.cpu_count() or 8)
    # Device of the index build's embedding model: "cpu" (FastEmbed) or "cuda"
    # (PyTorch fp16, needs the GPU environment). Queries always run on the CPU.
    embedding_device: str = "cpu"
    conditions_file: Path = CORPUS_DATA_DIR / "medical_conditions.jsonl"
    herbs_file: Path = CORPUS_DATA_DIR / "herbs.jsonl"
    frontend_dist_dir: Path = ROOT / "src" / "frontend" / "dist"
    database_url: str = "postgresql://medicina:medicina@127.0.0.1:5432/medicina"
    temp_dir: Path = Path(
        "/tmp/naturist-sessions" if os.name != "nt" else str(ROOT / "var" / "sessions")
    )
    xai_model: str = "grok-4.3"
    xai_reasoning_effort: str = "medium"
    xai_max_context_chars: int = 1_000_000
    xai_api_base: str = "https://api.x.ai/v1"
    ai_provider: str = "xai"
    hf_model: str = "deepseek-ai/DeepSeek-V4-Flash:deepinfra"
    hf_api_base: str = "https://router.huggingface.co/v1"
    hf_reasoning_effort: str = ""
    hf_max_context_chars: int = 120_000
    ollama_model: str = "deepseek-v4.1-flash:cloud"
    ollama_api_base: str = "http://localhost:11434/v1"
    ollama_reasoning_effort: str = ""
    ollama_max_context_chars: int = 1_000_000
    deepseek_model: str = "deepseek-flash"
    deepseek_api_base: str = "https://api.deepseek.com"
    deepseek_reasoning_effort: str = ""
    deepseek_max_context_chars: int = 1_000_000
    # Identification of a condition the dictionary does not know (ai/condition_ai.py):
    # backends are tried in order; the local one is an Ollama model, the other
    # goes through the Hugging Face router (HF_API_BASE, HF_TOKEN).
    condition_ai_backends: tuple[str, ...] = ("local", "huggingface")
    condition_ai_hf_model: str = "deepseek-ai/DeepSeek-V4-Flash:deepinfra"
    condition_ai_local_model: str = "gemma3:1b"
    condition_ai_local_base: str = "http://localhost:11434/v1"
    condition_ai_timeout_seconds: int = 10
    condition_ai_max_output_tokens: int = 300
    ai_stream: bool = False
    ai_max_output_tokens: int = 20000
    ai_read_timeout_seconds: int = 300
    session_idle_seconds: int = 3600
    session_max_seconds: int = 14400
    max_chat_chars: int = 4000
    max_requests_per_minute: int = 60
    log_level: str = "INFO"
    log_fragment_text: bool = True
    log_fragment_text_max_chars: int = 4000
    log_ai_response_text: bool = False

    max_active_sessions: int = 100
    max_sessions_per_cookie: int = 1
    max_sessions_per_ip: int = 1
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
    operation_timeout_seconds: int = 600
    operation_reservation_bytes: int = 65536
    owner_key: str = field(default="", repr=False)
    cookie_secure: bool = False
    public_root_path: str = ""
    public_origin: str = ""

    @classmethod
    def from_env(cls, env=None, *, dotenv: bool = False) -> "Settings":
        """Read configuration explicitly; tests pass a mapping and never load .env."""
        if dotenv:
            load_dotenv(ROOT / ".env", override=False)
        env = os.environ if env is None else env
        return cls(
            documents_dir=Path(
                env.get("DOCUMENTS_DIR", str(CORPUS_DATA_DIR / "documents"))
            ),
            model_cache_dir=Path(env.get("MODEL_CACHE_DIR", str(ROOT / "model_cache"))),
            embedding_threads=_int(
                "EMBEDDING_THREADS", min(8, os.cpu_count() or 8), env=env
            ),
            embedding_device=_embedding_device(env=env),
            conditions_file=Path(
                env.get(
                    "CONDITIONS_FILE", str(CORPUS_DATA_DIR / "medical_conditions.jsonl")
                )
            ),
            herbs_file=Path(
                env.get("HERBS_FILE", str(CORPUS_DATA_DIR / "herbs.jsonl"))
            ),
            frontend_dist_dir=Path(
                env.get("FRONTEND_DIST_DIR", str(ROOT / "src" / "frontend" / "dist"))
            ),
            database_url=env.get(
                "DATABASE_URL", "postgresql://medicina:medicina@127.0.0.1:5432/medicina"
            ),
            temp_dir=Path(
                env.get(
                    "SESSION_TEMP_DIR",
                    "/tmp/naturist-sessions"
                    if os.name != "nt"
                    else str(ROOT / "var" / "sessions"),
                )
            ),
            xai_model=env.get("XAI_MODEL", "grok-4.3"),
            xai_reasoning_effort=env.get("XAI_REASONING_EFFORT", "medium"),
            xai_max_context_chars=_int("X_AI_MAX_CONTEXT_CHARS", 1000000, env=env),
            xai_api_base=env.get("XAI_API_BASE", "https://api.x.ai/v1").rstrip("/"),
            ai_provider=_ai_provider(env=env),
            hf_model=env.get("HF_MODEL", "deepseek-ai/DeepSeek-V4-Flash:deepinfra"),
            hf_api_base=env.get(
                "HF_API_BASE", "https://router.huggingface.co/v1"
            ).rstrip("/"),
            hf_reasoning_effort=env.get("HF_REASONING_EFFORT", "").strip(),
            hf_max_context_chars=_int("HF_MAX_CONTEXT_CHARS", 120000, env=env),
            ollama_model=env.get("OLLAMA_MODEL", "deepseek-v4.1-flash:cloud"),
            ollama_api_base=env.get(
                "OLLAMA_API_BASE", "http://localhost:11434/v1"
            ).rstrip("/"),
            ollama_reasoning_effort=env.get("OLLAMA_REASONING_EFFORT", "").strip(),
            ollama_max_context_chars=_int("OLLAMA_MAX_CONTEXT_CHARS", 1000000, env=env),
            deepseek_model=env.get("DEEPSEEK_MODEL", "deepseek-flash"),
            deepseek_api_base=env.get(
                "DEEPSEEK_API_BASE", "https://api.deepseek.com"
            ).rstrip("/"),
            deepseek_reasoning_effort=env.get("DEEPSEEK_REASONING_EFFORT", "").strip(),
            deepseek_max_context_chars=_int(
                "DEEPSEEK_MAX_CONTEXT_CHARS", 1000000, env=env
            ),
            condition_ai_backends=_condition_ai_backends(env=env),
            condition_ai_hf_model=env.get(
                "CONDITION_AI_HF_MODEL",
                env.get("HF_MODEL", "deepseek-ai/DeepSeek-V4-Flash:deepinfra"),
            ),
            condition_ai_local_model=env.get("CONDITION_AI_LOCAL_MODEL", "gemma3:1b"),
            condition_ai_local_base=env.get(
                "CONDITION_AI_LOCAL_BASE", "http://localhost:11434/v1"
            ).rstrip("/"),
            condition_ai_timeout_seconds=_int(
                "CONDITION_AI_TIMEOUT_SECONDS", 10, env=env
            ),
            condition_ai_max_output_tokens=_int(
                "CONDITION_AI_MAX_OUTPUT_TOKENS", 300, env=env
            ),
            ai_stream=_bool("AI_STREAM", False, env=env),
            ai_max_output_tokens=_int("AI_MAX_OUTPUT_TOKENS", 20000, env=env),
            ai_read_timeout_seconds=_int("AI_READ_TIMEOUT_SECONDS", 300, env=env),
            session_idle_seconds=_int("SESSION_IDLE_SECONDS", 3600, env=env),
            session_max_seconds=_int("SESSION_MAX_SECONDS", 14400, env=env),
            max_chat_chars=_int("MAX_CHAT_CHARS", 4000, env=env),
            max_requests_per_minute=_int("MAX_REQUESTS_PER_MINUTE", 60, env=env),
            log_level=env.get("LOG_LEVEL", "INFO").strip().upper(),
            log_fragment_text=_bool("LOG_FRAGMENT_TEXT", True, env=env),
            log_fragment_text_max_chars=_int(
                "LOG_FRAGMENT_TEXT_MAX_CHARS", 4000, env=env
            ),
            log_ai_response_text=_bool("LOG_AI_RESPONSE_TEXT", False, env=env),
            max_active_sessions=_int("MAX_ACTIVE_SESSIONS", 100, env=env),
            max_sessions_per_cookie=_int("MAX_SESSIONS_PER_COOKIE", 1, env=env),
            max_sessions_per_ip=_int("MAX_SESSIONS_PER_IP", 1, env=env),
            new_sessions_per_ip_minute=_int("NEW_SESSIONS_PER_IP_MINUTE", 10, env=env),
            new_sessions_per_cookie_minute=_int(
                "NEW_SESSIONS_PER_COOKIE_MINUTE", 5, env=env
            ),
            max_history_bytes=_int("MAX_HISTORY_BYTES", 8388608, env=env),
            max_evidence_bytes=_int("MAX_EVIDENCE_BYTES", 25165824, env=env),
            max_pdf_bytes=_int("MAX_PDF_BYTES", 16777216, env=env),
            max_session_bytes=_int("MAX_SESSION_BYTES", 67108864, env=env),
            max_global_bytes=_int("MAX_GLOBAL_BYTES", 268435456, env=env),
            max_api_body_bytes=_int("MAX_API_BODY_BYTES", 262144, env=env),
            owner_login_per_minute=_int("OWNER_LOGIN_PER_MINUTE", 5, env=env),
            max_concurrent_searches=_int("MAX_CONCURRENT_SEARCHES", 2, env=env),
            max_concurrent_generations=_int("MAX_CONCURRENT_GENERATIONS", 1, env=env),
            operation_timeout_seconds=_int("OPERATION_TIMEOUT_SECONDS", 600, env=env),
            operation_reservation_bytes=_int(
                "OPERATION_RESERVATION_BYTES", 65536, env=env
            ),
            owner_key=env.get("OWNER_KEY", ""),
            cookie_secure=_bool("COOKIE_SECURE", False, env=env),
            public_root_path=env.get(
                "PUBLIC_ROOT_PATH", env.get("GRADIO_ROOT_PATH", "")
            ).rstrip("/"),
            public_origin=env.get("PUBLIC_ORIGIN", "").strip().rstrip("/"),
        )

    # Reject an unknown provider even when Settings is built directly (tests).
    def __post_init__(self) -> None:
        _ai_provider(self.ai_provider)
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
        for name in (
            "session_idle_seconds",
            "session_max_seconds",
            "max_requests_per_minute",
            "max_chat_chars",
            "max_active_sessions",
            "max_sessions_per_cookie",
            "max_sessions_per_ip",
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
            "operation_timeout_seconds",
            "operation_reservation_bytes",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.session_idle_seconds > self.session_max_seconds:
            raise ValueError("session_idle_seconds must not exceed session_max_seconds")
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


def configure_settings(value: Settings) -> None:
    """Configure legacy retrieval modules explicitly at runtime, before workers start."""
    from dataclasses import fields

    for item in fields(Settings):
        object.__setattr__(settings, item.name, getattr(value, item.name))
