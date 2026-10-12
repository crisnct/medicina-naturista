"""Small, validated intent decisions through the existing local Ollama model."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.ai.client import ResponsesClient
from backend.ai.providers import ProviderConfig
from backend.config import Settings

logger = logging.getLogger("naturist.classification")
MessageIntent = Literal["remedii", "planta", "diverse", "email_raport"]
PROMPT = Path(__file__).parent / "prompts" / "message_classification_system.md"


class MessageClassification(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    intent: MessageIntent
    herb_name: str | None = Field(default=None, min_length=1, max_length=160)
    email_address: str | None = Field(default=None, min_length=1, max_length=254)
    needs_clarification: bool = False

    @model_validator(mode="after")
    def valid_fields(self) -> MessageClassification:
        if self.intent != "planta" and self.herb_name is not None:
            raise ValueError("herb_name is only valid for planta")
        if self.intent != "email_raport" and self.email_address is not None:
            raise ValueError("email_address is only valid for email_raport")
        if self.intent == "planta" and not self.needs_clarification and not self.herb_name:
            raise ValueError("planta needs a name or clarification")
        return self


class MessageClassifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.prompt = PROMPT.read_text(encoding="utf-8").strip()
        self.client = ResponsesClient(
            ProviderConfig(
                name="ollama",
                label="Ollama (local)",
                base_url=settings.condition_ai_local_base,
                model=settings.condition_ai_local_model,
                reasoning_effort=None,
                api_key=lambda: "",
                api_key_env="",
                api_key_required=False,
                json_format=None,
                send_store=False,
                max_context_chars=0,
                max_output_tokens=settings.message_classification_max_output_tokens,
                read_timeout_seconds=settings.message_classification_timeout_seconds,
                stream=False,
                temperature=0.0,
            ),
            settings,
        )

    def __call__(self, message: str, context: dict[str, object]) -> MessageClassification:
        started = time.monotonic()
        try:
            raw = self.client.complete_json(
                self.prompt,
                json.dumps({"message": message, "context": context}, ensure_ascii=False),
                self.settings.message_classification_max_output_tokens,
            )
            result = MessageClassification.model_validate(raw)
            logger.info(
                "message_classified intent=%s duration_ms=%s",
                result.intent,
                round((time.monotonic() - started) * 1000),
            )
            return result
        except Exception as exc:
            logger.warning(
                "classification_failed type=%s reason=%s duration_ms=%s",
                type(exc).__name__,
                getattr(exc, "reason", "invalid_output"),
                round((time.monotonic() - started) * 1000),
            )
            raise

    def close(self) -> None:
        self.client.close()
