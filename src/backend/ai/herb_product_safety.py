"""Strict, concise product safety from local model knowledge, independent of the corpus."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from backend.ai.effort import responses_effort
from backend.ai.herb_association_rules import content_hash
from backend.ai.herbs import Herb
from backend.config import Settings
from backend.core.language import current_language, read_prompt
from backend.core.report_models import DEFAULT_REPORT_EFFORT

logger = logging.getLogger("naturist.ai")
MessageType = Literal["warning", "contraindication", "interaction"]
MESSAGE_TYPES = ("warning", "contraindication", "interaction")
MAX_CHARS = 240
MAX_WORDS = 40
PROMPT_PATH = Path(__file__).with_name("prompts") / "herb_product_safety_system.md"
# One prompt for both languages and both model stages; it never follows the application language.
BILINGUAL_PROMPT_PATH = (
    Path(__file__).with_name("prompts") / "herb_product_safety_bilingual_system.md"
)
DEDUP_PROMPT_PATH = Path(__file__).with_name("prompts") / "herb_product_safety_dedup_system.md"
Stage = Literal["ministral", "deepseek"]
STAGES: tuple[Stage, ...] = ("ministral", "deepseek")
BILINGUAL_VERSION = 2
# Bumped when the bilingual text validation changes, so earlier cached answers are asked again.
BILINGUAL_VALIDATION_VERSION = 3
# Most severe first; decides which of two equivalent messages of one source survives.
SEVERITY = {"contraindication": 0, "interaction": 1, "warning": 2}


def product_identity(herb: Herb) -> dict[str, Any]:
    identity = asdict(herb)
    for key in ("ro_regional", "latin_synonyms", "en_alt"):
        identity[key] = sorted(set(identity[key]))
    return identity


def catalog_identity(herbs: tuple[Herb, ...]) -> str:
    return content_hash([product_identity(herb) for herb in sorted(herbs, key=lambda h: h.id)])


def product_prompt() -> str:
    return read_prompt(PROMPT_PATH)


def product_semantic(settings: Settings) -> dict[str, Any]:
    return {
        "version": 1,
        "source": "model_knowledge",
        "language": current_language(),
        "prompt": content_hash(product_prompt()),
        "validation_version": 1,
        "max_chars": MAX_CHARS,
        "max_words": MAX_WORDS,
        "message_types": list(MESSAGE_TYPES),
        "model": settings.herb_association_ai_model,
        "temperature": 0,
    }


# Other products and corpus edits must not invalidate an unchanged product's answer.
def product_cache_key(herb: Herb, semantic: dict[str, Any], digest: str) -> str:
    return content_hash([product_identity(herb), semantic, digest])


def product_response_schema(herb_id: int) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["herb_id", "status", "messages"],
        "properties": {
            "herb_id": {"type": "integer", "const": herb_id},
            "status": {"type": "string", "enum": ["complete", "uncertain"]},
            "messages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["message_type", "problem"],
                    "properties": {
                        "message_type": {"type": "string", "enum": list(MESSAGE_TYPES)},
                        "problem": {"type": "string", "minLength": 1, "maxLength": MAX_CHARS},
                    },
                },
            },
        },
    }


@dataclass(frozen=True)
class ProductSafetyMessage:
    message_type: MessageType
    problem: str

    @property
    def identity(self) -> str:
        return content_hash([self.message_type, self.problem])


@dataclass(frozen=True)
class ProductSafetyResult:
    herb_id: int
    status: Literal["complete", "uncertain"]
    messages: tuple[ProductSafetyMessage, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "herb_id": self.herb_id,
            "status": self.status,
            "messages": [asdict(message) for message in self.messages],
        }


# One concise single-line text; shared by the monolingual and the bilingual validators.
def clean_problem(value: str) -> str:
    problem = value.strip()
    if (
        not problem
        or len(problem) > MAX_CHARS
        or len(problem.split()) > MAX_WORDS
        or "\n" in problem
        or "\r" in problem
        or any(ord(char) < 32 for char in problem)
        or re.match(r"^(?:[-*#•]|\d+[.)]\s)", problem)
    ):
        raise ValueError("HERB_PRODUCT_SAFETY_INVALID_MESSAGE")
    return problem


# A malformed or oversized answer is never truncated, repaired or cached as an empty result.
def validate_product_response(raw: Any, herb_id: int) -> ProductSafetyResult:
    if (
        not isinstance(raw, dict)
        or set(raw) != {"herb_id", "status", "messages"}
        or type(raw["herb_id"]) is not int
        or raw["herb_id"] != herb_id
        or raw["status"] not in ("complete", "uncertain")
        or not isinstance(raw["messages"], list)
    ):
        raise ValueError("HERB_PRODUCT_SAFETY_INVALID_RESPONSE")
    messages: dict[str, ProductSafetyMessage] = {}
    for item in raw["messages"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"message_type", "problem"}
            or item["message_type"] not in MESSAGE_TYPES
            or not isinstance(item["problem"], str)
        ):
            raise ValueError("HERB_PRODUCT_SAFETY_INVALID_MESSAGE")
        message = ProductSafetyMessage(item["message_type"], clean_problem(item["problem"]))
        messages[message.identity] = message
    return ProductSafetyResult(herb_id, raw["status"], tuple(messages.values()))


def serialize_product(herb: Herb) -> str:
    return json.dumps(
        {"product": product_identity(herb)}, ensure_ascii=False, separators=(",", ":")
    )


# --- Bilingual batch extension: one answer per product serves both languages. ---


def dedup_prompt() -> str:
    return DEDUP_PROMPT_PATH.read_text(encoding="utf-8").strip()


# Grouping equivalent messages is a separate local-model stage with its own cache identity.
def dedup_semantic(settings: Settings) -> dict[str, Any]:
    return {
        "version": BILINGUAL_VERSION,
        "source": "model_knowledge_bilingual",
        "stage": "dedup",
        "prompt": content_hash(dedup_prompt()),
        "model": settings.herb_safety_dedup_model,
        "temperature": 0,
    }


# The key covers the exact message list the model grouped, so any change to it re-asks.
def dedup_cache_key(
    herb_id: int, identities: Sequence[str], semantic: dict[str, Any], digest: str
) -> str:
    return content_hash(["dedup", herb_id, list(identities), semantic, digest])


def serialize_dedup_batch(items: Sequence[tuple[int, Sequence[BilingualMessage]]]) -> str:
    return json.dumps(
        {
            "products": [
                {
                    "herb_id": herb_id,
                    "messages": [
                        {"i": index, "type": message.message_type, "text": message.problem_en}
                        for index, message in enumerate(messages)
                    ],
                }
                for herb_id, messages in items
            ]
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def dedup_response_schema(sizes: dict[int, int]) -> dict[str, Any]:
    group = {
        "type": "array",
        "items": {"type": "integer", "minimum": 0, "maximum": max(sizes.values()) - 1},
        "minItems": 2,
    }
    product = {
        "type": "object",
        "additionalProperties": False,
        "required": ["herb_id", "groups"],
        "properties": {
            "herb_id": {"type": "integer", "enum": list(sizes)},
            "groups": {"type": "array", "items": group},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["products"],
        "properties": {
            "products": {
                "type": "array",
                "items": product,
                "minItems": len(sizes),
                "maxItems": len(sizes),
            }
        },
    }


# Every group needs at least two valid indexes. The model often names a message in two groups
# ([2, 9] and [11, 2]) or twice in one; that states that they are the same risk, so groups that
# share a message are joined and the result is the disjoint sets of equivalent messages.
def validate_dedup_groups(raw: Any, size: int) -> list[list[int]]:
    if not isinstance(raw, list):
        raise ValueError("HERB_PRODUCT_SAFETY_INVALID_RESPONSE")
    joined: list[set[int]] = []
    for group in raw:
        if (
            not isinstance(group, list)
            or len(group) < 2
            or any(type(index) is not int or not 0 <= index < size for index in group)
        ):
            raise ValueError("HERB_PRODUCT_SAFETY_INVALID_RESPONSE")
        members = set(group)
        if len(members) < 2:
            continue
        for other in [found for found in joined if found & members]:
            members |= other
            joined.remove(other)
        joined.append(members)
    return sorted(sorted(found) for found in joined)


# Same envelope rule as the generation stages: only broken products are left uncached.
def validate_dedup_response(
    raw: Any, sizes: dict[int, int]
) -> tuple[dict[int, list[list[int]]], list[int]]:
    if (
        not isinstance(raw, dict)
        or set(raw) != {"products"}
        or not isinstance(raw["products"], list)
    ):
        raise ValueError("HERB_PRODUCT_SAFETY_INVALID_RESPONSE")
    seen: set[int] = set()
    results: dict[int, list[list[int]]] = {}
    for entry in raw["products"]:
        herb_id = entry.get("herb_id") if isinstance(entry, dict) else None
        if type(herb_id) is not int or herb_id not in sizes or herb_id in seen:
            raise ValueError("HERB_PRODUCT_SAFETY_INVALID_RESPONSE")
        seen.add(herb_id)
        if set(entry) != {"herb_id", "groups"}:
            continue
        try:
            results[herb_id] = validate_dedup_groups(entry["groups"], sizes[herb_id])
        except ValueError:
            continue
    return results, [herb_id for herb_id in sizes if herb_id not in results]


@dataclass(frozen=True)
class BilingualMessage:
    message_type: MessageType
    problem_ro: str
    problem_en: str

    @property
    def identity(self) -> str:
        return content_hash([self.message_type, self.problem_ro, self.problem_en])


@dataclass(frozen=True)
class BilingualResult:
    herb_id: int
    status: Literal["complete", "uncertain"]
    messages: tuple[BilingualMessage, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "herb_id": self.herb_id,
            "status": self.status,
            "messages": [asdict(message) for message in self.messages],
        }


# The prompt file is read directly: it is the same for Romanian and English runs.
def bilingual_prompt() -> str:
    return BILINGUAL_PROMPT_PATH.read_text(encoding="utf-8").strip()


def serialize_batch(herbs: Sequence[Herb]) -> str:
    return json.dumps(
        {"products": [product_identity(herb) for herb in herbs]},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def batch_response_schema(herb_ids: Sequence[int]) -> dict[str, Any]:
    message = {
        "type": "object",
        "additionalProperties": False,
        "required": ["message_type", "problem_ro", "problem_en"],
        "properties": {
            "message_type": {"type": "string", "enum": list(MESSAGE_TYPES)},
            "problem_ro": {"type": "string", "minLength": 1, "maxLength": MAX_CHARS},
            "problem_en": {"type": "string", "minLength": 1, "maxLength": MAX_CHARS},
        },
    }
    product = {
        "type": "object",
        "additionalProperties": False,
        "required": ["herb_id", "status", "messages"],
        "properties": {
            "herb_id": {"type": "integer", "enum": list(herb_ids)},
            "status": {"type": "string", "enum": ["complete", "uncertain"]},
            "messages": {"type": "array", "items": message},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["products"],
        "properties": {
            "products": {
                "type": "array",
                "items": product,
                "minItems": len(herb_ids),
                "maxItems": len(herb_ids),
            }
        },
    }


# Small models sometimes mix another script into a word (a Cyrillic letter inside Romanian text).
def is_latin(text: str) -> bool:
    return all(
        not char.isalpha() or unicodedata.name(char, "").startswith("LATIN") for char in text
    )


# A malformed message rejects its whole product: there are no half-bilingual items.
def validate_bilingual_product(raw: Any, herb_id: int) -> BilingualResult:
    if (
        not isinstance(raw, dict)
        or set(raw) != {"herb_id", "status", "messages"}
        or type(raw["herb_id"]) is not int
        or raw["herb_id"] != herb_id
        or raw["status"] not in ("complete", "uncertain")
        or not isinstance(raw["messages"], list)
    ):
        raise ValueError("HERB_PRODUCT_SAFETY_INVALID_RESPONSE")
    messages: dict[str, BilingualMessage] = {}
    for item in raw["messages"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"message_type", "problem_ro", "problem_en"}
            or item["message_type"] not in MESSAGE_TYPES
            or not isinstance(item["problem_ro"], str)
            or not isinstance(item["problem_en"], str)
        ):
            raise ValueError("HERB_PRODUCT_SAFETY_INVALID_MESSAGE")
        message = BilingualMessage(
            item["message_type"],
            clean_problem(item["problem_ro"]),
            clean_problem(item["problem_en"]),
        )
        # A deterministic model repeats the same glitch on a retry, so only that one message is
        # left out (never edited); the remaining valid messages of the product are kept.
        if not (is_latin(message.problem_ro) and is_latin(message.problem_en)):
            logger.warning(
                "herb_safety_bilingual_message_dropped herb_id=%s reason=script", herb_id
            )
            continue
        messages[message.identity] = message
    return BilingualResult(herb_id, raw["status"], tuple(messages.values()))


# The envelope is all-or-nothing; inside a valid envelope only the broken products are dropped.
# Returns the valid answers by ID and the requested IDs that were invalid or missing.
def validate_batch_response(
    raw: Any, herb_ids: Sequence[int]
) -> tuple[dict[int, BilingualResult], list[int]]:
    if (
        not isinstance(raw, dict)
        or set(raw) != {"products"}
        or not isinstance(raw["products"], list)
    ):
        raise ValueError("HERB_PRODUCT_SAFETY_INVALID_RESPONSE")
    requested = set(herb_ids)
    seen: set[int] = set()
    results: dict[int, BilingualResult] = {}
    for entry in raw["products"]:
        herb_id = entry.get("herb_id") if isinstance(entry, dict) else None
        if type(herb_id) is not int or herb_id not in requested or herb_id in seen:
            raise ValueError("HERB_PRODUCT_SAFETY_INVALID_RESPONSE")
        seen.add(herb_id)
        try:
            results[herb_id] = validate_bilingual_product(entry, herb_id)
        except ValueError:
            continue
    return results, [herb_id for herb_id in herb_ids if herb_id not in results]


# A monolingual projection keeps order, type and count of the bilingual list.
def project_language(
    herb_id: int,
    status: Literal["complete", "uncertain"],
    messages: Sequence[BilingualMessage],
    language: str,
) -> ProductSafetyResult:
    return ProductSafetyResult(
        herb_id,
        status,
        tuple(
            ProductSafetyMessage(
                message.message_type, message.problem_ro if language == "ro" else message.problem_en
            )
            for message in messages
        ),
    )


def stage_semantic(settings: Settings, stage: Stage) -> dict[str, Any]:
    semantic: dict[str, Any] = {
        "version": BILINGUAL_VERSION,
        "source": "model_knowledge_bilingual",
        "stage": stage,
        "prompt": content_hash(bilingual_prompt()),
        "validation_version": BILINGUAL_VALIDATION_VERSION,
        "max_chars": MAX_CHARS,
        "max_words": MAX_WORDS,
        "message_types": list(MESSAGE_TYPES),
    }
    if stage == "ministral":
        return {**semantic, "model": settings.herb_safety_generation_model, "temperature": 0}
    return {
        **semantic,
        "model": settings.deepseek_model,
        "reasoning_effort": responses_effort(DEFAULT_REPORT_EFFORT),
    }


# An external API has no weights digest, so its model name inside the semantics is the identity.
def stage_cache_key(herb: Herb, semantic: dict[str, Any], digest: str | None) -> str:
    return content_hash([product_identity(herb), semantic, digest])


# Run semantics of a generation. Scope, batch sizes and the stage list decide how a generation was
# made, not whether it is still valid, so they stay out of the runtime comparison below.
def run_semantic(settings: Settings, language: str, stages: Sequence[Stage]) -> dict[str, Any]:
    return {
        "version": BILINGUAL_VERSION,
        "source": "model_knowledge_bilingual",
        "language": language,
        "prompt": content_hash(bilingual_prompt()),
        "validation_version": BILINGUAL_VALIDATION_VERSION,
        "max_chars": MAX_CHARS,
        "max_words": MAX_WORDS,
        "message_types": list(MESSAGE_TYPES),
        "model": settings.herb_safety_generation_model,
        "temperature": 0,
        "stages": list(stages),
        "deepseek_model": settings.deepseek_model if "deepseek" in stages else None,
        "dedup_prompt": content_hash(dedup_prompt()),
        "scope": settings.herb_safety_extension_products,
    }


RUNTIME_KEYS = (
    "version",
    "source",
    "language",
    "prompt",
    "validation_version",
    "max_chars",
    "max_words",
    "message_types",
)


# Whether a stored generation still matches this process: exact for the single-product flow,
# and prompt/validator/model/language for the bilingual extension.
def semantic_is_current(stored: Any, settings: Settings) -> bool:
    if not isinstance(stored, dict):
        return False
    if stored.get("version") != BILINGUAL_VERSION:
        return bool(stored == product_semantic(settings))
    expected = run_semantic(settings, current_language(), ())
    return all(stored.get(key) == expected[key] for key in RUNTIME_KEYS)
