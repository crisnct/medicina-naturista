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
MessageIntent = Literal["remedii", "planta", "diverse", "email_raport", "top_plante"]
PROMPT = Path(__file__).parent / "prompts" / "message_classification_system.md"


class MessageClassification(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    intent: MessageIntent
    herb_name: str | None = Field(default=None, min_length=1, max_length=160)
    email_address: str | None = Field(default=None, min_length=1, max_length=254)
    top_count: int | None = Field(default=None, ge=1, le=10000)
    needs_clarification: bool = False

    @model_validator(mode="after")
    def valid_fields(self) -> MessageClassification:
        if self.intent != "planta" and self.herb_name is not None:
            raise ValueError("herb_name is only valid for planta")
        if self.intent != "email_raport" and self.email_address is not None:
            raise ValueError("email_address is only valid for email_raport")
        if self.intent != "top_plante" and self.top_count is not None:
            raise ValueError("top_count is only valid for top_plante")
        if self.intent == "top_plante" and not self.needs_clarification and self.top_count is None:
            raise ValueError("top_plante needs a count or clarification")
        if self.intent == "planta" and not self.needs_clarification and not self.herb_name:
            raise ValueError("planta needs a name or clarification")
        return self


def explicit_remedy_request(message: str) -> MessageClassification | None:
    """A single explicit remedy request already supplies its intent and subject."""
    normalized = _normalize(message)
    if normalized in {"remedii", "remedii naturale", "remedii naturiste", "tratamente naturiste"}:
        return MessageClassification(intent="remedii", needs_clarification=True)
    match = re.fullmatch(
        r"(?:(?:te|va) rog )?"
        r"(?:(?:cauta|caut|vreau|doresc|as vrea|da mi|recomanda mi|arata mi|gaseste mi|gaseste) )?"
        r"(?:remedii(?:le)?|tratamente(?:le)?)(?: (?:naturale|naturiste))? "
        r"(?:pentru|contra|impotriva) (.+)",
        normalized,
    )
    if match is None:
        return None
    # Compound commands, quoted/negative requests and unrelated actions still
    # need semantic classification. Several conditions are one remedy request.
    if (
        "@" in message
        or re.search(
            r"\b(email|mail|raport|trimite|trimiterea|top|compara|nu cauta|nu vreau)\b",
            normalized,
        )
        or re.search(r"[\"«»„”]", message)
    ):
        return None
    if match[1] in {"mine", "noi", "asta", "aceasta", "ceva", "o afectiune"}:
        return MessageClassification(intent="remedii", needs_clarification=True)
    return MessageClassification(intent="remedii")


def explicit_herb_top(message: str, context: dict[str, object]) -> MessageClassification | None:
    """Resolve explicit general catalog rankings even when Ollama is unavailable."""
    normalized = _normalize(message)
    if context.get("pending_clarification") == "top_plante" and re.fullmatch(
        r"\d{1,5}", normalized
    ):
        count = int(normalized)
    else:
        plants = re.search(r"\bplante(?:le)?\b", normalized)
        if plants is None:
            return None
        # A medical qualifier (even without "pentru") must reach the semantic
        # classifier rather than being mistaken for the general catalog top.
        generic_tail = {
            "care",
            "sunt",
            "cele",
            "mai",
            "recomandate",
            "utile",
            "bune",
            "folosite",
            "medicinale",
            "eficiente",
            "populare",
            "si",
            "din",
            "catalog",
            "lista",
            "in",
            "general",
            "te",
            "rog",
        }
        if set(re.findall(r"\w+", normalized[plants.end() :])) - generic_tail:
            return None
        if re.search(r"\b(pentru|contra|impotriva|email|mail|raport|nu)\b|@", normalized):
            return None
        if re.search(r"\b(?:in|la)\s+(?!general\b)\w+", normalized):
            return None
        match = re.search(r"\b(?:top|primele)\s+(\d{1,5})\b", normalized)
        if match is None:
            match = re.search(r"\b(\d{1,5})\s+(?:de\s+)?plante\b", normalized)
            if match is None or not re.search(r"\b(recomandate|utile|bune|folosite)\b", normalized):
                return None
        count = int(match[1])
    if not 1 <= count <= 10000:
        return MessageClassification(intent="top_plante", needs_clarification=True)
    return MessageClassification(intent="top_plante", top_count=count)


def complete_general_question(message: str) -> bool:
    """Recognize a named informational subject without authorizing another action."""
    normalized = _normalize(message)
    match = re.fullmatch(
        r"(?:(?:te|va) rog )?"
        r"(?:(?:spune mi(?: tot ce stii)?|ce (?:stii|imi poti spune)|"
        r"(?:vreau|doresc|as vrea) (?:informatii|detalii)|informatii|detalii) despre|"
        r"despre|cine (?:este|a fost)|cum functioneaza) (.+)",
        normalized,
    )
    if match is None or "@" in message or re.search(r"[;\n]", message):
        return False
    subject = match[1].strip()
    if subject in {"asta", "acesta", "aceasta", "ceva", "el", "ea", "ei", "ele"}:
        return False
    # Incomplete plant/remedy requests and compound commands still need the
    # model's clarification; a general question never authorizes an email.
    return not re.search(
        r"\b(planta|plante|remediu|remedii|tratament|tratamente|afectiune|boala|"
        r"trimite|email|mail|raport|top|cauta|recomanda)\b",
        subject,
    )


def explicit_herb_request(message: str, catalog: HerbCatalog) -> MessageClassification | None:
    """Resolve a request about a catalog plant without relying on a model label."""

    def decision(name: str) -> MessageClassification | None:
        matches = catalog.request_matches(name)
        if not matches:
            return None
        if len(matches) == 1:
            herb = matches[0]
            # Keep species-specific aliases specific when the primary name is shared.
            name = herb.ro if len(catalog.lookup(herb.ro)) == 1 else herb.latin
        return MessageClassification(intent="planta", herb_name=name)

    bare = decision(message.strip())
    if bare is not None:
        return bare
    normalized = _normalize(message)
    match = re.fullmatch(
        r"(?:(?:te|va) rog )?"
        r"(?:(?:spune mi(?: tot ce stii)?|ce (?:stii|imi poti spune)|"
        r"(?:vreau|doresc|as vrea) (?:informatii|detalii)|informatii|detalii) despre|"
        r"despre|la ce (?:e|este|sunt) (?:bun|buna|buni|bune)) (.+)",
        normalized,
    )
    if match is None:
        return None
    subject = re.sub(r"^planta | te rog$", "", match[1])
    # A shared name reaches the species-selection flow without choosing a plant.
    return decision(subject)


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
                model=settings.medical_condition_ai_local_model,
                # Keep the bounded output budget for the final routing JSON.
                reasoning_effort="none",
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
                                "top_count",
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
                                "top_count": {
                                    "type": ["integer", "null"]
                                    if intent == "top_plante"
                                    else "null",
                                    **(
                                        {"minimum": 1, "maximum": 10000}
                                        if intent == "top_plante"
                                        else {}
                                    ),
                                },
                            },
                        }
                        for intent in ("remedii", "planta", "diverse", "email_raport", "top_plante")
                    ],
                },
            ),
            settings,
        )

    def __call__(self, message: str, context: dict[str, object]) -> MessageClassification:
        started = time.monotonic()
        try:
            explicit = explicit_remedy_request(message) or explicit_herb_top(message, context)
            if explicit is not None:
                logger.info(
                    "message_classified intent=%s needs_clarification=%s source=explicit duration_ms=%s",
                    explicit.intent,
                    explicit.needs_clarification,
                    round((time.monotonic() - started) * 1000),
                )
                return explicit
            catalog = None
            candidates: list[str] = []
            if self.herb_catalog is not None:
                try:
                    catalog = self.herb_catalog()
                    candidates = sorted({herb.ro for herb in catalog.mentions(message)})
                except HerbCatalogUnavailable:
                    logger.warning("classification_catalog_unavailable")
            choices = context.get("herb_choices")
            selected = (
                catalog.selected_choice(
                    message, [choice for choice in choices if isinstance(choice, str)]
                )
                if catalog is not None
                and isinstance(choices, (list, tuple))
                and context.get("pending_clarification") == "planta"
                else None
            )
            named_request = (
                MessageClassification(intent="planta", herb_name=selected.latin)
                if selected is not None
                else explicit_herb_request(message, catalog)
                if catalog is not None
                else None
            )
            if named_request is not None:
                logger.info(
                    "message_classified intent=planta needs_clarification=false source=catalog duration_ms=%s",
                    round((time.monotonic() - started) * 1000),
                )
                return named_request
            context = {**context, "recognized_herbs": candidates[:10]}
            raw = self.client.complete_json(
                self.prompt,
                json.dumps({"message": message, "context": context}, ensure_ascii=False),
                self.settings.message_classification_max_output_tokens,
            )
            if isinstance(raw, dict) and catalog is not None:
                exact_names = {herb.ro for herb in catalog.lookup(message)}
                # A bare catalog name is a complete plant request, including replies to
                # clarification. It never authorizes an email or changes a remedy question.
                if exact_names and raw.get("intent") in {"planta", "diverse", "remedii"}:
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
            if (
                isinstance(raw, dict)
                and raw.get("intent") == "diverse"
                and raw.get("needs_clarification") is True
                and not candidates
                and complete_general_question(message)
            ):
                # A complete general question needs no missing plant, condition
                # or answer from the classifier before retrieval can start.
                raw = {**raw, "needs_clarification": False}
            result = MessageClassification.model_validate(raw)
            logger.info(
                "message_classified intent=%s needs_clarification=%s source=model duration_ms=%s",
                result.intent,
                result.needs_clarification,
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
