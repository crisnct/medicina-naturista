"""Bounded local-only polarity classification; validated quotations are source provenance."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import httpx

from backend.ai.client import OllamaReportClient, ResponsesClient
from backend.ai.herb_association_rules import (
    EXCEPTION,
    LABELS,
    RULES_VERSION,
    SCHEMA_VERSION,
    Candidate,
    Decision,
    Label,
    Unit,
    content_hash,
    source_context,
)
from backend.ai.herb_index_catalog import normalize_herb_name
from backend.ai.providers import ProviderConfig
from backend.config import Settings
from backend.core.operation_context import checkpoint, remaining_timeout

PROMPT_PATH = Path(__file__).parent / "prompts" / "herb_association_classification_system.md"
TRANSPORT_PATH = PROMPT_PATH.with_name("herb_association_classification_transport.md")
Work = tuple[Unit, Candidate]
CODE_LABELS: tuple[Label, ...] = ("unclear", "positive", "caution", "mixed")


def classification_prompt() -> str:
    return "\n\n".join(
        path.read_text(encoding="utf-8").strip() for path in (PROMPT_PATH, TRANSPORT_PATH)
    )


# Every mention remains available for final coverage, although inference owns one relation.
def group_works(works: list[Work] | tuple[Work, ...]) -> list[tuple[Work, tuple[Work, ...]]]:
    grouped: dict[tuple[str, int, int], list[Work]] = defaultdict(list)
    for unit, candidate in works:
        grouped[(unit.identity, candidate.herb_id, candidate.condition_id)].append(
            (unit, candidate)
        )
    return [
        (
            (
                members[0][0],
                replace(
                    members[0][1],
                    mentions=tuple(sorted({candidate.mention for _, candidate in members})),
                ),
            ),
            tuple(members),
        )
        for members in grouped.values()
    ]


# Reference source spans by short IDs so the model cannot paraphrase a provenance quotation.
def quotation_spans(
    text: str, prefix: str = "", *, max_chars: int = 1000
) -> dict[str, tuple[int, int]]:
    if type(max_chars) is not int or not 1 <= max_chars <= 1000:
        raise ValueError("POSITIVE_INVALID_PASSAGE_LIMIT")
    spans: dict[str, tuple[int, int]] = {}
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        # OCR soft wraps must not separate a product, its effect and its warning.
        boundaries = list(re.finditer(r"[.!?;](?=\s)|\n\s*\n", text[start:end]))
        if end < len(text) and boundaries:
            end = start + boundaries[-1].end()
        elif end < len(text):
            space = text.rfind(" ", start + 1, end)
            if space > start:
                end = space + 1
        if len(text) - start <= max_chars and not text[end:].strip():
            end = len(text)
        spans[f"{prefix}q{len(spans)}"] = (start, end)
        start = end
    return spans


# Every output key and quotation reference is constrained by this exact request.
def response_schema(payload: dict[str, Any]) -> dict[str, Any]:
    definitions = {
        key: {
            "type": "string",
            "enum": [
                part["id"]
                for segment in unit["segments"]
                for part in segment["parts"]
                if part["text"].strip()
            ],
        }
        for key, unit in payload["units"].items()
    }
    for key in payload["units"]:
        definitions[f"{key}_decision"] = {
            "anyOf": [
                {
                    "type": "array",
                    # Native Ollama's grammar accepts draft-7 tuple items, not prefixItems.
                    "items": [
                        {"type": "integer", "const": code},
                        *[{"$ref": f"#/$defs/{key}"}] * count,
                    ],
                    "additionalItems": False,
                    "minItems": count + 1,
                    "maxItems": count + 1,
                }
                for code, count in [
                    (0, 0),
                    (1, 1),
                    (2, 1),
                    (3, 1),
                    (3, 2),
                ]
            ]
        }
    # Relations in one unit share a grammar, including that unit's exclusive quote enum.
    properties = {
        candidate["id"]: {"$ref": f"#/$defs/{candidate['unit']}_decision"}
        for candidate in payload["candidates"]
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["relations"],
        "$defs": definitions,
        "properties": {
            "relations": {
                "type": "object",
                "additionalProperties": False,
                "required": list(properties),
                "properties": properties,
            }
        },
    }


class AssociationClient(OllamaReportClient):
    # This client is owned by one serial preparation worker, never shared with report jobs.
    def complete_json(self, system: str, user: str, max_tokens: int) -> dict[str, Any]:
        self.provider = replace(self.provider, response_schema=response_schema(json.loads(user)))
        return super().complete_json(system, user, max_tokens)


def semantic_config(settings: Settings) -> dict[str, Any]:
    return {
        "rules": RULES_VERSION,
        "schema": SCHEMA_VERSION,
        "prompt": content_hash(PROMPT_PATH.read_text(encoding="utf-8").strip()),
        "transport": content_hash(TRANSPORT_PATH.read_text(encoding="utf-8").strip()),
        "transport_policy": content_hash(Path(__file__).read_text(encoding="utf-8")),
        "rules_policy": content_hash(
            Path(__file__).with_name("herb_association_rules.py").read_text(encoding="utf-8")
        ),
        "catalog_policy": content_hash(
            Path(__file__).with_name("herb_positive_repository.py").read_text(encoding="utf-8")
        ),
        "cache_semantics": 1,
        "model": settings.herb_association_ai_model,
        "context": settings.herb_association_ai_context_tokens,
        "temperature": 0,
    }


def relation_id(work: Work) -> str:
    unit, candidate = work
    return content_hash([unit.identity, asdict(candidate)])


def cache_key(work: Work, semantic: dict[str, Any], digest: str) -> str:
    unit, candidate = work
    # Document/chunk IDs and timeouts are intentionally absent from semantic cache identity.
    policy = {
        key: value
        for key, value in semantic.items()
        if key
        not in {
            "rules",
            "rules_policy",
            "catalog_policy",
            "schema",
            "transport",
            "transport_policy",
        }
    }
    return content_hash([unit.text, source_context(unit), asdict(candidate), policy, digest])


# Short batch-unique references reduce decoding without changing canonical source offsets.
def _batch_quotations(batch: list[Work], max_chars: int) -> dict[str, dict[str, tuple[int, int]]]:
    result: dict[str, dict[str, tuple[int, int]]] = {}
    position = 0
    for unit, _ in batch:
        if unit.identity in result:
            continue
        quotes = {}
        for start, end in quotation_spans(unit.text, max_chars=max_chars).values():
            for a, b in quotation_spans(
                unit.text[start:end], max_chars=min(320, max_chars)
            ).values():
                value = position + 1
                identifier = ""
                while value:
                    value, digit = divmod(value - 1, 26)
                    identifier = chr(ord("a") + digit) + identifier
                quotes[identifier] = (start + a, start + b)
                position += 1
        result[unit.identity] = quotes
    return result


def serialize_batch(
    batch: list[Work],
    names: dict[int, str],
    conditions: dict[int, str],
    *,
    max_passage_chars: int = 1000,
) -> str:
    units = {}
    unit_ids: dict[str, str] = {}
    relations = []
    quotations = _batch_quotations(batch, max_passage_chars)
    for position, work in enumerate(batch):
        unit, candidate = work
        unit_key = unit_ids.setdefault(unit.identity, f"u{len(unit_ids)}")
        if unit_key not in units:
            units[unit_key] = {
                "segments": [
                    {
                        "start": start,
                        "parts": [
                            {"id": identifier, "start": a, "text": unit.text[a:b]}
                            for identifier, (a, b) in quotations[unit.identity].items()
                            if start <= a < b <= end
                        ],
                    }
                    for start, end in quotation_spans(
                        unit.text, max_chars=max_passage_chars
                    ).values()
                ],
                **source_context(unit),
            }
        relations.append(
            {
                "id": f"r{position}",
                "unit": unit_key,
                "herb_id": candidate.herb_id,
                "herb": names[candidate.herb_id],
                "condition_id": candidate.condition_id,
                "condition": conditions[candidate.condition_id],
                "mentions": candidate.mentions or (candidate.mention,),
                "mention_texts": [
                    unit.text[a:b] for a, b in (candidate.mentions or (candidate.mention,))
                ],
                "mention_quotes": [
                    [
                        identifier
                        for identifier, (x, y) in quotations[unit.identity].items()
                        if x < b and y > a
                    ]
                    for a, b in (candidate.mentions or (candidate.mention,))
                ],
            }
        )
    return json.dumps(
        {"units": units, "candidates": relations},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def pack_batches(
    works: list[Work],
    settings: Settings,
    names: dict[int, str],
    conditions: dict[int, str],
    *,
    prompt: str | None = None,
) -> list[list[Work]]:
    prompt = classification_prompt() if prompt is None else prompt

    def fits(batch: list[Work]) -> bool:
        serialized = serialize_batch(
            batch,
            names,
            conditions,
            max_passage_chars=settings.herb_association_ai_max_passage_chars,
        )
        payload = json.loads(serialized)
        envelope = json.dumps(
            {
                "model": settings.herb_association_ai_model,
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": serialized},
                ],
                "stream": False,
                "format": response_schema(payload),
                "truncate": False,
                "shift": False,
                "think": False,
                "options": {
                    "num_predict": settings.herb_association_ai_max_output_tokens,
                    "num_ctx": settings.herb_association_ai_context_tokens,
                    "temperature": 0.0,
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        size = len(envelope)
        # UTF-8 bytes are a conservative token upper bound, not a characters/token estimate.
        tokens_upper = len(envelope.encode()) + 512
        return (
            len(batch) <= min(20, settings.herb_association_ai_max_pairs)
            and (
                sum(len(unit["segments"]) for unit in payload["units"].values())
                <= min(6, settings.herb_association_ai_max_units)
                # An oversized source unit owns its request; its warnings stay together.
                or len(payload["units"]) == 1
            )
            and size <= min(25000, settings.herb_association_ai_max_input_chars)
            and tokens_upper + settings.herb_association_ai_max_output_tokens
            <= settings.herb_association_ai_context_tokens
        )

    # Bucket short simple units by primary disease; complex units never share requests.
    buckets: dict[tuple[str, object], list[Work]] = defaultdict(list)
    for work in works:
        unit, candidate = work
        text = normalize_herb_name(unit.text)
        nutrient_table = (
            any(normalize_herb_name(h) == "nutrienti" for h in unit.headings)
            or re.search(r"\bsupliment doza(?: recomandata)?\b|\bsupliment dozarecomandata\b", text)
        ) and re.search(r"\b(?:mg|mcg|ui)\b|\bconform indicatiilor\b", text)
        simple = (
            not nutrient_table
            and len(unit.text) <= settings.herb_association_ai_max_passage_chars
            and "|" not in unit.text
            and len(unit.passage.primary) == 1
            and len({c.condition_id for c in unit.candidates}) == 1
            and len(
                {
                    identifier
                    for identifier, (a, b) in unit.condition_mentions
                    if len(normalize_herb_name(unit.text[a:b])) >= 4
                }
            )
            <= 1
            and not EXCEPTION.search(normalize_herb_name(unit.text))
        )
        key = ("condition", candidate.condition_id) if simple else ("unit", unit.identity)
        buckets[key].append(work)
    result: list[list[Work]] = []
    for bucket in buckets.values():
        start = 0
        while start < len(bucket):
            # Prefix size only grows; find the largest admissible batch without serializing
            # every relation twice. The final prefix uses the exact serialized envelope.
            end = start
            stop = min(len(bucket), start + min(20, settings.herb_association_ai_max_pairs)) + 1
            while end + 1 < stop:
                middle = (end + stop) // 2
                if fits(bucket[start:middle]):
                    end = middle
                else:
                    stop = middle
            if end == start:
                unit, _ = bucket[start]
                raise ValueError(f"POSITIVE_UNIT_TOO_LARGE:{unit.passage.chunk_id}:{unit.start}")
            result.append(bucket[start:end])
            start = end
    return result


def validate_response(
    raw: Any, batch: list[Work], *, max_passage_chars: int = 1000
) -> dict[str, Decision]:
    if (
        not isinstance(raw, dict)
        or set(raw) != {"relations"}
        or not isinstance(raw["relations"], dict)
    ):
        raise ValueError("POSITIVE_INVALID_RESPONSE")
    expected = {f"r{position}": work for position, work in enumerate(batch)}
    if raw["relations"].keys() != expected.keys():
        raise ValueError("POSITIVE_INCOMPLETE_RESPONSE")
    decisions = {}
    quotations = _batch_quotations(batch, max_passage_chars)
    for identifier, entry in raw["relations"].items():
        if (
            not isinstance(entry, list)
            or not entry
            or type(entry[0]) is not int
            or entry[0] not in range(4)
        ):
            raise ValueError("POSITIVE_INVALID_RELATION")
        label, quotes = CODE_LABELS[entry[0]], entry[1:]
        if (
            not isinstance(identifier, str)
            or identifier not in expected
            or not isinstance(label, str)
            or label not in LABELS
            or not isinstance(quotes, list)
            or len(quotes)
            not in ((0,) if label == "unclear" else (1, 2) if label == "mixed" else (1,))
        ):
            raise ValueError("POSITIVE_INVALID_RELATION")
        unit, _ = expected[identifier]
        allowed_quotes = quotations[unit.identity]
        spans = []
        for quote in quotes:
            if (
                not isinstance(quote, str)
                or quote not in allowed_quotes
                or not unit.text[slice(*allowed_quotes[quote])].strip()
            ):
                raise ValueError("POSITIVE_INVALID_QUOTE")
            if allowed_quotes[quote] not in spans:
                spans.append(allowed_quotes[quote])
        decisions[relation_id(expected[identifier])] = Decision(label, "model", "", tuple(spans))
    return decisions


# Cached canonical source offsets are independent of wire IDs and segment boundaries.
def validate_cached(decision: Decision, work: Work) -> None:
    unit, _ = work
    if (
        decision.origin != "model"
        or decision.label not in LABELS
        or len(decision.quotes)
        not in (
            (0,) if decision.label == "unclear" else (1, 2) if decision.label == "mixed" else (1,)
        )
        or len(set(decision.quotes)) != len(decision.quotes)
    ):
        raise ValueError("POSITIVE_INVALID_CACHE")
    for a, b in decision.quotes:
        if (
            type(a) is not int
            or type(b) is not int
            or not 0 <= a < b <= len(unit.text)
            or not unit.text[a:b].strip()
        ):
            raise ValueError("POSITIVE_INVALID_CACHE")


def model_digest(settings: Settings) -> str:
    with httpx.Client(trust_env=False, follow_redirects=False) as http:
        response = http.get(
            settings.herb_association_ai_base.removesuffix("/v1") + "/api/tags",
            timeout=remaining_timeout(settings.herb_association_ai_timeout_seconds),
        )
        response.raise_for_status()
        models = response.json().get("models", [])
    checkpoint()
    for model in models:
        if model.get("name") == settings.herb_association_ai_model:
            digest = model.get("digest")
            if isinstance(digest, str) and re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", digest):
                return digest
    raise ValueError("POSITIVE_MODEL_UNAVAILABLE")


def make_client(settings: Settings) -> ResponsesClient:
    provider = ProviderConfig(
        name="ollama",
        label="Ollama (local)",
        base_url=settings.herb_association_ai_base,
        model=settings.herb_association_ai_model,
        reasoning_effort=None,
        api_key=lambda: "",
        api_key_env="",
        api_key_required=False,
        json_format="response_format",
        send_store=False,
        max_context_chars=settings.herb_association_ai_max_input_chars,
        max_output_tokens=settings.herb_association_ai_max_output_tokens,
        read_timeout_seconds=settings.herb_association_ai_timeout_seconds,
        stream=False,
        temperature=0.0,
        response_schema=None,
        context_tokens=settings.herb_association_ai_context_tokens,
        thinking=False,
    )
    client = AssociationClient(
        provider,
        replace(settings, ai_stream=False, log_fragment_text=False, log_ai_response_text=False),
    )
    # Local classification must ignore HTTP proxy environment variables as well as redirects.
    client.http.close()
    client.http = httpx.Client(trust_env=False, follow_redirects=False)
    return client
