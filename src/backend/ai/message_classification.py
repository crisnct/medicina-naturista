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
from backend.ai.query_terms import plain
from backend.config import Settings
from backend.core.herb_categories import (
    CATEGORY_ALIASES,
    GLOBAL_TOP_ALIASES,
    HERB_CATEGORIES,
    HerbCategory,
    TopClarification,
)

logger = logging.getLogger("naturist.classification")
MessageIntent = Literal["remedii", "planta", "diverse", "email_raport", "top_plante"]
PROMPT = Path(__file__).parent / "prompts" / "message_classification_system.md"


class MessageClassification(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    intent: MessageIntent
    herb_name: str | None = Field(default=None, min_length=1, max_length=160)
    email_address: str | None = Field(default=None, min_length=1, max_length=254)
    top_count: int | None = Field(default=None, ge=1, le=10000)
    top_category: HerbCategory | None = None
    top_condition: str | None = Field(default=None, min_length=1, max_length=240)
    top_clarification: TopClarification | None = None
    needs_clarification: bool = False

    @model_validator(mode="after")
    def valid_fields(self) -> MessageClassification:
        if self.intent != "planta" and self.herb_name is not None:
            raise ValueError("herb_name is only valid for planta")
        if self.intent != "email_raport" and self.email_address is not None:
            raise ValueError("email_address is only valid for email_raport")
        if self.intent != "top_plante" and any(
            value is not None
            for value in (
                self.top_count,
                self.top_category,
                self.top_condition,
                self.top_clarification,
            )
        ):
            raise ValueError("top_count is only valid for top_plante")
        if self.intent == "top_plante" and not self.needs_clarification and self.top_count is None:
            raise ValueError("top_plante needs a count or clarification")
        if self.intent == "top_plante":
            if self.top_condition is not None and not self.top_condition.strip():
                raise ValueError("top_condition must name a subject")
            if self.needs_clarification != (self.top_clarification is not None):
                raise ValueError("top clarification needs an explicit reason")
            if self.top_clarification == "count" and self.top_count is not None:
                raise ValueError("count clarification must not include a count")
            if self.top_clarification == "category" and self.top_category is not None:
                raise ValueError("category clarification must not select a category")
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


# A longer category phrase owns its span; a separate generic phrase still counts.
def _top_categories(normalized: str) -> set[HerbCategory]:
    matches = [
        (category, match.start(), match.end())
        for category, aliases in CATEGORY_ALIASES.items()
        for alias in aliases
        for match in re.finditer(r"\b" + re.escape(alias) + r"\b", normalized)
    ]
    return {
        category
        for category, start, end in matches
        if not any(
            other_start <= start and end <= other_end and (other_start < start or end < other_end)
            for _, other_start, other_end in matches
        )
    }


def _top_decision(
    count: int | None,
    category: HerbCategory | None,
    *,
    unknown: bool = False,
    condition: str | None = None,
    missing_condition: bool = False,
) -> MessageClassification:
    reason: TopClarification | None = (
        "category"
        if unknown
        else "condition"
        if missing_condition
        else "count"
        if count is None or not 1 <= count <= 10000
        else None
    )
    return MessageClassification(
        intent="top_plante",
        top_count=count if count is not None and 1 <= count <= 10000 else None,
        top_category=None if unknown else category,
        top_condition=condition,
        top_clarification=reason,
        needs_clarification=reason is not None,
    )


def _condition_herb_top(message: str, context: dict[str, object]) -> MessageClassification | None:
    normalized = _normalize(message)
    if re.search(r'["«»„”\n;]', message) or re.search(
        r"\b(email|mail|raport|nu|compara|trimite)\b|@", normalized
    ):
        return None
    parts = re.split(r"\b(?:pentru|contra|[iî]mpotriva)\b", message, maxsplit=1, flags=re.I)
    if len(parts) == 2:
        base = explicit_herb_top(parts[0].strip(), {}, for_condition=True)
        if base is not None:
            subject = _normalize(parts[1])
            missing = subject in {"", "o afectiune", "ceva", "asta", "mine", "noi"}
            missing = missing or len(subject) > 240
            return _top_decision(
                base.top_count,
                base.top_category,
                unknown=base.top_clarification == "category",
                condition=None if missing else subject,
                missing_condition=missing,
            )
    if context.get("pending_clarification") != "top_plante":
        return None
    saved = context.get("top_condition")
    condition = saved if isinstance(saved, str) else None
    reason = context.get("top_clarification")
    count = context.get("top_count")
    count = count if type(count) is int else None
    category = context.get("top_category")
    category = category if category in HERB_CATEGORIES else None
    if reason == "condition":
        # New complete commands belong to their own route, even during clarification.
        if complete_general_question(message) or re.search(
            r"\b(top|topul|primele|cele mai|remedii|tratamente|despre|cauta|cum|ce|la ce)\b",
            normalized,
        ):
            return None
        if re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", message.strip()):
            choices = context.get("top_condition_choices")
            position = int(message.strip()) if re.fullmatch(r"\d+", message.strip()) else 0
            if isinstance(choices, (list, tuple)) and 1 <= position <= len(choices):
                choice = choices[position - 1]
                if isinstance(choice, str):
                    return _top_decision(count, category, condition=choice)
            return _top_decision(
                count, category, condition=condition, missing_condition=condition is None
            )
        subject = _normalize(parts[1]) if len(parts) == 2 and not parts[0].strip() else normalized
        if subject and len(subject) <= 240:
            return _top_decision(count, category, condition=subject)
        return _top_decision(count, category, condition=condition, missing_condition=True)
    if (condition is not None or context.get("top_condition_required") is True) and reason in {
        "count",
        "category",
    }:
        base = explicit_herb_top(
            message,
            {
                **context,
                "top_condition": None,
                "top_condition_choices": (),
                "top_condition_required": False,
            },
        )
        if base is not None:
            # Only short replies inherit the disease; a new top replaces the old request.
            if re.search(r"\b(top|topul|primele|cele mai)\b", normalized):
                return base
            return _top_decision(
                base.top_count,
                base.top_category,
                unknown=base.top_clarification == "category",
                condition=condition,
                missing_condition=condition is None,
            )
    return None


def explicit_herb_top(
    message: str, context: dict[str, object], *, for_condition: bool = False
) -> MessageClassification | None:
    """Resolve complete rankings and short replies without model or catalog I/O."""
    condition_top = _condition_herb_top(message, context)
    if condition_top is not None:
        return condition_top
    if (
        context.get("pending_clarification") == "top_plante"
        and context.get("top_clarification") == "condition"
        and re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", message.strip())
    ):
        return None
    normalized = _normalize(message)
    numeric = re.search(r"(?<!\w)[+-]?\d+(?:[.,]\d+)?", message)
    if numeric is not None:
        # Text normalization discards signs and decimal punctuation; quantities must not.
        normalized = normalized.replace(_normalize(numeric[0]), numeric[0], 1)
    if normalized == "toate categoriile" and context.get("pending_clarification") != "top_plante":
        return _top_decision(100, None)
    if re.search(r'["«»„”\n;]', message) or re.search(
        r"\b(pentru|contra|impotriva|email|mail|raport|nu|compara|trimite)\b|@", normalized
    ):
        return None
    pending = context.get("pending_clarification") == "top_plante"
    if pending and re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", normalized):
        if context.get("top_clarification") == "category":
            selection = int(normalized) if re.fullmatch(r"\d+", normalized) else 0
            count = context.get("top_count")
            return _top_decision(
                count if type(count) is int else None,
                HERB_CATEGORIES[selection - 1] if 1 <= selection <= len(HERB_CATEGORIES) else None,
                unknown=not 1 <= selection <= len(HERB_CATEGORIES),
            )
        category = context.get("top_category")
        category = category if category in HERB_CATEGORIES else None
        return _top_decision(
            int(normalized) if re.fullmatch(r"[+-]?\d+", normalized) else None,
            category,
            unknown=context.get("top_clarification") == "category",
        )
    if pending:
        if (
            context.get("top_clarification") == "category"
            and not re.search(r"\b(top|topul|primele|cele mai)\b", normalized)
            and (normalized in GLOBAL_TOP_ALIASES or _top_categories(normalized))
        ):
            count = context.get("top_count")
            return _top_decision(count if type(count) is int else None, None, unknown=True)
        for category, aliases in CATEGORY_ALIASES.items():
            if normalized in aliases:
                count = context.get("top_count")
                return _top_decision(count if type(count) is int else None, category)
        if normalized in GLOBAL_TOP_ALIASES and normalized:
            count = context.get("top_count")
            return _top_decision(count if type(count) is int else None, None)
    match = re.fullmatch(
        r"(?:(?:te|va) rog )?(?:(?:da mi|arata mi|vreau|doresc|as vrea) )?"
        r"(?:(?:top(?:ul)?|primele)\b|(?:care sunt )?cele mai (?:utile|recomandate|bune|folosite))"
        r"(?:\s+([+-]?\d+(?:[.,]\d+)?))?(?:\s+(.*))?",
        normalized,
    )
    if match is None:
        return None
    raw_count, domain = match.groups()
    count = (
        100
        if raw_count is None
        else int(raw_count)
        if re.fullmatch(r"[+-]?\d+", raw_count)
        else None
    )
    domain = re.sub(r"^de | te rog$", "", domain or "")
    domain = re.sub(
        r"\b(care|sunt|cele|mai|recomandate|utile|bune|folosite|eficiente|populare)\b", "", domain
    )
    domain = re.sub(r"\b(din catalog|din lista|in general)\b", "", domain)
    domain = " ".join(domain.split())
    for category, aliases in CATEGORY_ALIASES.items():
        if domain in aliases:
            return _top_decision(count, category)
    if domain in GLOBAL_TOP_ALIASES:
        return _top_decision(
            count,
            None,
            unknown=not for_condition and domain in {"produse naturiste", "produsele naturiste"},
        )
    categories = _top_categories(domain)
    if len(categories) > 1 or not categories and not re.match(r"plante(?:le)?\b", domain):
        return _top_decision(count, None, unknown=True)
    if len(categories) == 1:
        category = next(iter(categories))
        remainder = domain
        for alias in sorted(CATEGORY_ALIASES[category], key=len, reverse=True):
            remainder = re.sub(r"\b" + re.escape(alias) + r"\b", " ", remainder)
        if not re.sub(r"\bsi\b", "", remainder).strip():
            return _top_decision(count, category)
    # Unknown qualifiers after a known group may be a medical subject. The model
    # must decide the intent; its ranking decision is still scope-checked below.
    return None


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
            name = herb.ro if len(catalog.lookup(herb.ro)) == 1 else (herb.latin or herb.ro)
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


def _semantic_condition_top(raw: dict[str, object], message: str) -> MessageClassification:
    validated = MessageClassification.model_validate(raw)
    condition = validated.top_condition
    # Category words and digits inside the disease name are never ranking parameters.
    parts = re.split(r"\b(?:pentru|contra|impotriva)\b", plain(message), maxsplit=1)
    header = parts[0]
    if len(parts) == 2:
        condition = _normalize(parts[1]) or None
    elif condition is not None:
        if plain(condition) not in header:
            condition = None
        else:
            header = header.replace(plain(condition), " ")
    if condition is not None and len(condition) > 240:
        condition = None
    scopes = _top_categories(_normalize(header))
    quantities = re.findall(r"(?<!\w)[+-]?\d+(?:[.,]\d+)?", header)
    count: int | None = validated.top_count if validated.top_count is not None else 100
    if quantities:
        count = (
            int(quantities[0])
            if len(quantities) == 1 and re.fullmatch(r"[+-]?\d+", quantities[0])
            else None
        )
    return _top_decision(
        count,
        next(iter(scopes)) if len(scopes) == 1 else None,
        unknown=len(scopes) > 1
        or not scopes
        and (
            validated.top_category is not None
            or validated.top_clarification == "category"
            or not re.search(
                r"\b(plante|produse(?:le)? naturiste|general|toate categoriile)\b", header
            )
        ),
        condition=condition,
        missing_condition=condition is None,
    )


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
                                "top_category",
                                "top_condition",
                                "top_clarification",
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
                                "top_category": {
                                    "enum": [*HERB_CATEGORIES, None]
                                    if intent == "top_plante"
                                    else [None],
                                },
                                "top_condition": {
                                    "type": ["string", "null"]
                                    if intent == "top_plante"
                                    else "null",
                                    **(
                                        {"minLength": 1, "maxLength": 240}
                                        if intent == "top_plante"
                                        else {}
                                    ),
                                },
                                "top_clarification": {
                                    "enum": ["count", "category", "condition", None]
                                    if intent == "top_plante"
                                    else [None],
                                },
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
                MessageClassification(intent="planta", herb_name=selected.latin or selected.ro)
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
            if isinstance(raw, dict) and raw.get("intent") == "top_plante":
                if (
                    raw.get("top_condition") is not None
                    or raw.get("top_clarification") == "condition"
                    or re.search(r"\b(pentru|contra|impotriva)\b", _normalize(message))
                ):
                    return _semantic_condition_top(raw, message)
                scopes = _top_categories(_normalize(message))
                if len(scopes) > 1:
                    raw = {
                        **raw,
                        "top_category": None,
                        "top_clarification": "category",
                        "needs_clarification": True,
                    }
                elif scopes:
                    # A semantic decision cannot widen an explicitly requested scope.
                    raw = {**raw, "top_category": next(iter(scopes))}
                elif raw.get("top_category") is not None or not re.search(
                    r"\b(produse naturiste|general|toate categoriile)\b|"
                    r"\bplante(?:le)?(?: (?:care|sunt|cele|mai|utile|recomandate|bune|folosite|"
                    r"din|catalog|in|lista|general))*$",
                    _normalize(message),
                ):
                    explicit_quantities = re.findall(r"(?<!\w)[+-]?\d+(?:[.,]\d+)?", message)
                    count = (
                        int(explicit_quantities[0])
                        if len(explicit_quantities) == 1
                        and re.fullmatch(r"[+-]?\d+", explicit_quantities[0])
                        else None
                        if explicit_quantities
                        else raw.get("top_count")
                    )
                    return _top_decision(count if type(count) is int else None, None, unknown=True)
                quantities = re.findall(r"(?<!\w)[+-]?\d+(?:[.,]\d+)?", message)
                if quantities:
                    valid_count = (
                        int(quantities[0])
                        if len(quantities) == 1 and re.fullmatch(r"[+-]?\d+", quantities[0])
                        else None
                    )
                    if valid_count is None or not 1 <= valid_count <= 10000:
                        return _top_decision(
                            None,
                            next(iter(scopes)) if len(scopes) == 1 else None,
                            unknown=len(scopes) > 1,
                        )
                    raw = {**raw, "top_count": valid_count}
                elif raw.get("top_count") is None and raw.get("needs_clarification") is False:
                    raw = {**raw, "top_count": 100}
                if (
                    not scopes
                    and re.search(r"\bproduse(?:le)? naturiste\b", _normalize(message))
                    and not re.search(r"\btoate categoriile\b", _normalize(message))
                ):
                    count = raw.get("top_count")
                    return _top_decision(count if type(count) is int else None, None, unknown=True)
                try:
                    result = MessageClassification.model_validate(raw)
                except ValueError:
                    return _top_decision(
                        None,
                        next(iter(scopes)) if len(scopes) == 1 else None,
                        unknown=len(scopes) != 1,
                    )
            else:
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
