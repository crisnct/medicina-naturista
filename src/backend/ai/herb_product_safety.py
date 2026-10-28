"""Strict, concise product safety from local model knowledge, independent of the corpus."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from backend.ai.herb_association_rules import content_hash
from backend.ai.herbs import Herb
from backend.config import Settings

MessageType = Literal["warning", "contraindication", "interaction"]
MESSAGE_TYPES = ("warning", "contraindication", "interaction")
MAX_CHARS = 240
MAX_WORDS = 40
PROMPT_PATH = Path(__file__).with_name("prompts") / "herb_product_safety_system.md"


def product_identity(herb: Herb) -> dict[str, Any]:
    identity = asdict(herb)
    for key in ("ro_regional", "latin_synonyms", "en_alt"):
        identity[key] = sorted(set(identity[key]))
    return identity


def catalog_identity(herbs: tuple[Herb, ...]) -> str:
    return content_hash([product_identity(herb) for herb in sorted(herbs, key=lambda h: h.id)])


def product_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def product_semantic(settings: Settings) -> dict[str, Any]:
    return {
        "version": 1,
        "source": "model_knowledge",
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
        problem = item["problem"].strip()
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
        message = ProductSafetyMessage(item["message_type"], problem)
        messages[message.identity] = message
    return ProductSafetyResult(herb_id, raw["status"], tuple(messages.values()))


def serialize_product(herb: Herb) -> str:
    return json.dumps(
        {"product": product_identity(herb)}, ensure_ascii=False, separators=(",", ":")
    )
