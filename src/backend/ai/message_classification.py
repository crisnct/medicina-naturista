"""Small, validated intent decisions through the existing local Ollama model."""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.ai.client import ResponsesClient
from backend.ai.conditions import _normalize
from backend.ai.herb_repository import HerbCatalogUnavailable
from backend.ai.herbs import HerbCatalog
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
    def __init__(
        self, settings: Settings, herb_catalog: Callable[[], HerbCatalog] | None = None
    ) -> None:
        self.settings = settings
        self.herb_catalog = herb_catalog
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
                response_schema={
                    "oneOf": [
                        {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "intent",
                                "herb_name",
                                "email_address",
                                "needs_clarification",
                            ],
                            "properties": {
                                "intent": {"type": "string", "enum": [intent]},
                                "herb_name": {
                                    "type": ["string", "null"] if intent == "planta" else "null"
                                },
                                "email_address": {
                                    "type": ["string", "null"]
                                    if intent == "email_raport"
                                    else "null"
                                },
                                "needs_clarification": {"type": "boolean"},
                            },
                        }
                        for intent in ("remedii", "planta", "diverse", "email_raport")
                    ],
                },
            ),
            settings,
        )

    def __call__(self, message: str, context: dict[str, object]) -> MessageClassification:
        started = time.monotonic()
        try:
            catalog = None
            candidates: list[str] = []
            if self.herb_catalog is not None:
                try:
                    catalog = self.herb_catalog()
                    candidates = sorted({herb.ro for herb in catalog.mentions(message)})
                except HerbCatalogUnavailable:
                    logger.warning("classification_catalog_unavailable")
            context = {**context, "recognized_herbs": candidates[:10]}
            raw = self.client.complete_json(
                self.prompt,
                json.dumps({"message": message, "context": context}, ensure_ascii=False),
                self.settings.message_classification_max_output_tokens,
            )
            if isinstance(raw, dict) and catalog is not None:
                choices = context.get("herb_choices")
                selected = (
                    catalog.selected_choice(
                        message, [choice for choice in choices if isinstance(choice, str)]
                    )
                    if isinstance(choices, (list, tuple))
                    and context.get("pending_clarification") == "planta"
                    else None
                )
                exact_names = {herb.ro for herb in catalog.lookup(message)}
                # A bare catalog name is a complete plant request, including replies to
                # clarification. It never authorizes an email or changes a remedy question.
                if selected is not None and raw.get("intent") in {"planta", "diverse", "remedii"}:
                    raw = {
                        **raw,
                        "intent": "planta",
                        "herb_name": selected.latin,
                        "email_address": None,
                        "needs_clarification": False,
                    }
                elif exact_names and raw.get("intent") in {"planta", "diverse", "remedii"}:
                    raw = {
                        **raw,
                        "intent": "planta",
                        "herb_name": next(iter(exact_names))
                        if len(exact_names) == 1
                        else message.strip(),
                        "email_address": None,
                        "needs_clarification": False,
                    }
                elif raw.get("intent") == "planta":
                    named_tokens = catalog.mentioned_names(message)
                    if len(candidates) > 1 and len(named_tokens) > 1:
                        raw = {**raw, "herb_name": None, "needs_clarification": True}
                    elif (
                        candidates
                        and len(named_tokens) == 1
                        and not re.search(
                            r"\b(si|sau|ori|versus|vs|compara|comparatie|email|mail|raport)\b",
                            _normalize(message),
                        )
                        and "@" not in message
                    ):
                        # Resolve an explicitly named, unambiguous catalog plant rather
                        # than trusting a small model's spurious missing-name flag.
                        raw = {
                            **raw,
                            "herb_name": candidates[0] if len(candidates) == 1 else named_tokens[0],
                            "needs_clarification": False,
                        }
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
