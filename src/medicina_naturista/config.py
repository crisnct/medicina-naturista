"""Environment-backed settings. No patient data belongs in configuration or logs."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
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


@dataclass(frozen=True)
class Settings:
    documents_dir: Path = Path(os.getenv("DOCUMENTS_DIR", str(ROOT / "data" / "documents")))
    index_dir: Path = Path(os.getenv("INDEX_DIR", str(ROOT / "data" / "hybrid_index")))
    temp_dir: Path = Path(os.getenv("SESSION_TEMP_DIR", "/tmp/naturist-sessions" if os.name != "nt" else str(ROOT / "var" / "sessions")))
    xai_model: str = os.getenv("XAI_MODEL", "grok-4.3")
    xai_reasoning_effort: str = os.getenv("XAI_REASONING_EFFORT", "medium")
    xai_api_base: str = os.getenv("XAI_API_BASE", "https://api.x.ai/v1").rstrip("/")
    session_idle_seconds: int = _int("SESSION_IDLE_SECONDS", 3600)
    session_max_seconds: int = _int("SESSION_MAX_SECONDS", 14400)
    max_chat_chars: int = _int("MAX_CHAT_CHARS", 4000)
    max_requests_per_minute: int = _int("MAX_REQUESTS_PER_MINUTE", 60)
    min_relevance_percent: int = _int("MIN_RELEVANCE_PERCENT", 10, minimum=0, maximum=100)
    max_context_chars: int = _int("MAX_CONTEXT_CHARS", 2_400_000)
    log_level: str = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    log_fragment_text: bool = _bool("LOG_FRAGMENT_TEXT", True)
    log_fragment_text_max_chars: int = _int("LOG_FRAGMENT_TEXT_MAX_CHARS", 4000)
    log_ai_response_text: bool = _bool("LOG_AI_RESPONSE_TEXT", False)
    log_ai_response_text_max_chars: int = _int("LOG_AI_RESPONSE_TEXT_MAX_CHARS", 8000)

    # Return the configured xAI API key without surrounding whitespace.
    def api_key(self) -> str:
        return os.getenv("GROK_API_KEY_MED", "").strip()


settings = Settings()
