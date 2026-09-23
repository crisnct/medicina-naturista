"""Environment-backed settings. No patient data belongs in configuration or logs."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)


def _int(name: str, default: int, minimum: int = 1) -> int:
    value = int(os.getenv(name, str(default)))
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


@dataclass(frozen=True)
class Settings:
    documents_dir: Path = Path(os.getenv("DOCUMENTS_DIR", str(ROOT / "documents")))
    index_dir: Path = Path(os.getenv("INDEX_DIR", str(ROOT / "embedings")))
    temp_dir: Path = Path(os.getenv("SESSION_TEMP_DIR", "/tmp/naturist-sessions" if os.name != "nt" else str(ROOT / ".session_tmp")))
    xai_model: str = os.getenv("XAI_MODEL", "grok-4.3")
    xai_reasoning_effort: str = os.getenv("XAI_REASONING_EFFORT", "low")
    xai_api_base: str = os.getenv("XAI_API_BASE", "https://api.x.ai/v1").rstrip("/")
    session_idle_seconds: int = _int("SESSION_IDLE_SECONDS", 3600)
    session_max_seconds: int = _int("SESSION_MAX_SECONDS", 14400)
    max_chat_chars: int = _int("MAX_CHAT_CHARS", 4000)
    max_requests_per_minute: int = _int("MAX_REQUESTS_PER_MINUTE", 60)

    def api_key(self) -> str:
        return os.getenv("GROK_API_KEY_MED", "").strip()


settings = Settings()
