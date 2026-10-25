"""Bounded local-only polarity classification; validated quotations are source provenance."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import httpx

from backend.ai.client import OllamaReportClient, ResponsesClient
from backend.ai.herb_association_rules import (
    EXCEPTION,
    NEGATIVE,
    RULES_VERSION,
    SCHEMA_VERSION,
    Candidate,
    Decision,
    Label,
    Unit,
    content_hash,
    source_context,
)
from backend.ai.herb_association_scope import LocalConditionScope
from backend.ai.herb_index_catalog import normalize_herb_name
from backend.ai.providers import ProviderConfig
from backend.config import Settings
from backend.core.operation_context import checkpoint, remaining_timeout

PROMPT_PATH = Path(__file__).parent / "prompts" / "herb_association_classification_system.md"
TRANSPORT_PATH = PROMPT_PATH.with_name("herb_association_classification_transport.md")
Work = tuple[Unit, Candidate]
CODE_LABELS: tuple[Label, ...] = ("unclear", "positive", "caution")


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


# Local rules retain their original scope; inference and persisted quotes share chunk offsets.
@dataclass(frozen=True)
class FragmentWorkGroup:
    work: Work
    originals: tuple[Work, ...]
    evidence: tuple[Work, ...]


def group_fragment_works(
    works: list[Work] | tuple[Work, ...], conditions: dict[int, str]
) -> list[FragmentWorkGroup]:
    fragments: dict[int, list[Work]] = defaultdict(list)
    for work in works:
        fragments[work[0].passage.chunk_id].append(work)
    canonical = {normalize_herb_name(name): identifier for identifier, name in conditions.items()}
    result = []
    for originals in fragments.values():
        passage = originals[0][0].passage
        candidates = {
            (candidate.herb_id, candidate.condition_id, unit.start + a, unit.start + b)
            for unit, candidate in originals
            for a, b in (candidate.mentions or (candidate.mention,))
        }
        full = Unit(
            passage,
            0,
            len(passage.text),
            (passage.heading,),
            tuple(
                Candidate(herb, condition, (a, b)) for herb, condition, a, b in sorted(candidates)
            ),
            len(passage.primary) == 1,
            scope_conditions=tuple(
                sorted(
                    {
                        canonical[normalized]
                        for name in passage.primary
                        if (normalized := normalize_herb_name(name)) in canonical
                    }
                )
            ),
            condition_mentions=tuple(
                sorted(
                    {
                        (identifier, (unit.start + a, unit.start + b))
                        for unit, _ in originals
                        for identifier, (a, b) in unit.condition_mentions
                    }
                )
            ),
        )
        pairs: dict[tuple[int, int], list[Work]] = defaultdict(list)
        for original in originals:
            pairs[(original[1].herb_id, original[1].condition_id)].append(original)
        for (herb, condition), members in pairs.items():
            evidence = tuple(
                (
                    full,
                    Candidate(
                        herb, condition, (unit.start + c.mention[0], unit.start + c.mention[1])
                    ),
                )
                for unit, c in members
            )
            mentions = tuple(sorted({candidate.mention for _, candidate in evidence}))
            if len(mentions) != len(evidence):
                raise ValueError("POSITIVE_DUPLICATE_FRAGMENT_MENTION")
            result.append(
                FragmentWorkGroup(
                    (full, Candidate(herb, condition, mentions[0], mentions)),
                    tuple(members),
                    evidence,
                )
            )
    return result


# An explicit list remains source evidence when the model omits its recommendation.
def verified_recommendation(
    work: Work, *, condition_name: str, scope_catalog: LocalConditionScope
) -> Decision | None:
    unit, candidate = work
    source = unit.text
    for a, b in candidate.mentions or (candidate.mention,):
        if any(
            other.herb_id != candidate.herb_id and other.mention == (a, b)
            for other in unit.candidates
        ):
            continue
        start = source.rfind("\n", 0, a) + 1
        end = source.find("\n", b)
        end = len(source) if end < 0 else end
        prefix = source[start:a]
        if ":" not in prefix or re.search(r"[.!?]", prefix):
            continue
        if not re.match(
            r"^(?:[qoui] )?(?:alimente|plante|produse|suplimente|uleiuri)(?:le)? "
            r"(?:naturiste |medicinale |esentiale |volatile )?recomandat\w*\b",
            normalize_herb_name(prefix),
        ):
            continue
        statement = normalize_herb_name(source[start:end])
        if EXCEPTION.search(statement) or NEGATIVE.search(statement):
            continue
        if scope_catalog.verifies(unit, candidate, condition_name, None, (start, end)):
            return Decision(
                "positive", "rule", "explicit_scoped_recommendation_v6", ((start, end),)
            )
    return None


# Partition concise provenance spans locally after inference; these spans are not sent to Ollama.
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


# Every output relation and field is constrained by this exact request.
def response_schema(payload: dict[str, Any]) -> dict[str, Any]:
    properties = {}
    for candidate in payload["candidates"]:
        fields = {
            "local_condition": {"type": "string", "maxLength": 120},
            "recommendation": {"type": "boolean"},
            "prohibition": {"type": "boolean"},
        }
        properties[candidate["id"]] = {
            "type": "object",
            "properties": fields,
            "required": list(fields),
            "additionalProperties": False,
        }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["relations"],
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
        "cache_semantics": 6,
        "scope_policy": content_hash(
            Path(__file__).with_name("herb_association_scope.py").read_text(encoding="utf-8")
        ),
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


# Keep model input whole and derive concise evidence spans only for persisted provenance.
def _evidence_span(unit: Unit, candidate: Candidate, max_chars: int) -> tuple[int, int]:
    # Keep persisted provenance concise without dividing the text sent to the model.
    mentions = candidate.mentions or (candidate.mention,)
    return next(
        (
            (start, end)
            for start, end in quotation_spans(unit.text, max_chars=max_chars).values()
            if any(
                start < mention_end and end > mention_start
                for mention_start, mention_end in mentions
            )
        ),
        candidate.mention,
    )


def serialize_batch(
    batch: list[Work],
    names: dict[int, str],
    conditions: dict[int, str],
    *,
    condition_synonyms: dict[int, tuple[str, ...]] | None = None,
) -> str:
    units = {}
    unit_ids: dict[str, str] = {}
    relations = []
    for position, work in enumerate(batch):
        unit, candidate = work
        unit_key = unit_ids.setdefault(unit.identity, f"u{len(unit_ids)}")
        if unit_key not in units:
            context = source_context(unit)
            units[unit_key] = {
                "text": unit.text,
                "headings": context["headings"],
                "introductions": context["introductions"],
                "table_header": context["table_header"],
            }
        relations.append(
            {
                "id": f"r{position}",
                "unit": unit_key,
                "herb_id": candidate.herb_id,
                "herb": names[candidate.herb_id],
                "condition_id": candidate.condition_id,
                "condition": conditions[candidate.condition_id],
                "condition_synonyms": list(
                    (condition_synonyms or {}).get(candidate.condition_id, ())
                ),
                "mentions": candidate.mentions or (candidate.mention,),
                "mention_texts": [
                    unit.text[a:b] for a, b in (candidate.mentions or (candidate.mention,))
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
    condition_synonyms: dict[int, tuple[str, ...]] | None = None,
    prompt: str | None = None,
) -> list[list[Work]]:
    prompt = classification_prompt() if prompt is None else prompt

    def fits(batch: list[Work]) -> bool:
        serialized = serialize_batch(
            batch,
            names,
            conditions,
            condition_synonyms=condition_synonyms,
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
        # Character budgets bound memory; Ollama enforces its real token window with
        # truncate=false and shift=false. UTF-8 bytes are not a usable tokenizer here.
        return (
            len(batch) <= min(20, settings.herb_association_ai_max_pairs)
            and (
                len(payload["units"]) <= min(6, settings.herb_association_ai_max_units)
                # A long indexed fragment owns its request; its warnings stay together.
                or len(payload["units"]) == 1
            )
            and size <= settings.herb_association_ai_max_input_chars
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
    raw: Any,
    batch: list[Work],
    *,
    scope_catalog: LocalConditionScope,
    max_passage_chars: int = 1000,
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
    for identifier, entry in raw["relations"].items():
        fields = {"local_condition", "recommendation", "prohibition"}
        if (
            not isinstance(entry, dict)
            or set(entry) != fields
            or not isinstance(entry["local_condition"], str)
            or len(entry["local_condition"]) > 120
            or type(entry["recommendation"]) is not bool
            or type(entry["prohibition"]) is not bool
        ):
            raise ValueError("POSITIVE_INVALID_RELATION")
        unit, candidate = expected[identifier]
        evidence_span = _evidence_span(unit, candidate, max_passage_chars)
        label: Label = "unclear"
        spans: tuple[tuple[int, int], ...] = ()
        if scope_catalog.verifies(
            unit,
            candidate,
            entry["local_condition"],
            None,
            evidence_span,
        ):
            label = (
                "positive"
                if entry["recommendation"]
                else "caution"
                if entry["prohibition"]
                else "unclear"
            )
            if label != "unclear":
                spans = (evidence_span,)
        decisions[relation_id(expected[identifier])] = Decision(label, "model", "", spans)
    return decisions


# Cached canonical source offsets are independent of the full-text wire representation.
def validate_cached(decision: Decision, work: Work) -> None:
    unit, _ = work
    if (
        decision.origin != "model"
        or decision.label not in CODE_LABELS
        or len(decision.quotes) not in ((0,) if decision.label == "unclear" else (1,))
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
