"""Identification of the condition a message names when the dictionary does not
know it (data/medical_conditions.txt, see ai/conditions.py).

The segments of the message go to a small AI model, which answers, per segment,
with a condition name and a few synonyms — the shape of one dictionary line. The
answer becomes an ordinary `Condition` and its segment a `whole_condition`
segment (with_ai_conditions()), so search, chat and PDF treat it exactly like a
condition from the dictionary. Backends (CONDITION_AI_BACKENDS) are tried in
order: a local Ollama model and/or the Hugging Face router. Any failure means
"not identified"; it never breaks the search."""
from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from backend.ai import conditions
from backend.ai.client import AIUnavailable, ResponsesClient
from backend.ai.conditions import Condition, QuerySegment, ResolvedQuery, _normalize, resolve_query
from backend.ai.providers import ProviderConfig
from backend.config import settings

logger = logging.getLogger("naturist.condition_ai")

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "condition_identification_system.md"
MAX_NAME_CHARS = 100
MAX_SYNONYMS = 8
CACHE_SIZE = 128

# Why the step ended the way it did (AIConditionResult.reason).
IDENTIFIED = "identified"
NONE = "none"
DISABLED = "disabled"
NO_TOKEN = "no_token"
TIMEOUT = "timeout"
ERROR = "error"


@dataclass(frozen=True)
class AIConditionResult:
    # One entry per identified segment: {"index" (1-based position in
    # ResolvedQuery.segments), "name", "terms" (the name first, then its synonyms)}.
    # Plain dicts, so they live in the session profile and travel to the report.
    answers: tuple[dict[str, Any], ...] = ()
    backend: str = ""
    reason: str = NONE

    @property
    def identified(self) -> bool:
        return bool(self.answers)

    @property
    def conditions(self) -> tuple[Condition, ...]:
        return tuple(Condition(answer["name"], tuple(answer["terms"])) for answer in self.answers)


class _BackendFailure(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# The provider configuration of one backend; both speak the Responses API.
def _provider(backend: str) -> ProviderConfig:
    common = {
        "reasoning_effort": None,
        "json_format": None,
        "send_store": False,
        "max_context_chars": 0,
        "max_output_tokens": settings.condition_ai_max_output_tokens,
        "read_timeout_seconds": settings.condition_ai_timeout_seconds,
        "stream": False,
    }
    if backend == "huggingface":
        return ProviderConfig(
            name="huggingface",
            label="Hugging Face",
            base_url=settings.hf_api_base,
            model=settings.condition_ai_hf_model,
            api_key=settings.hf_token,
            api_key_env="HF_TOKEN",
            api_key_required=True,
            **common,
        )
    return ProviderConfig(
        name="ollama",
        label="Ollama (local)",
        base_url=settings.condition_ai_local_base,
        model=settings.condition_ai_local_model,
        api_key=lambda: "",
        api_key_env="",
        api_key_required=False,
        # A small model follows the JSON format far more reliably without sampling noise.
        temperature=0.0,
        **common,
    )


_clients: dict[tuple[str, str, str], ResponsesClient] = {}


# One client per backend and endpoint, kept for the life of the process.
def _client(backend: str) -> ResponsesClient:
    provider = _provider(backend)
    key = (backend, provider.base_url, provider.model)
    if key not in _clients:
        _clients[key] = ResponsesClient(provider, replace(settings, ai_stream=False))
    return _clients[key]


@lru_cache(maxsize=1)
def _system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def _user_message(texts: tuple[str, ...]) -> str:
    return "\n".join(f"{number}. {text}" for number, text in enumerate(texts, start=1))


# Keep the model's answer only as far as its form is right (not its content: the
# condition need not exist in the dictionary): a valid segment index, a non-empty
# name of at most MAX_NAME_CHARS, and a list of up to MAX_SYNONYMS other strings.
def _validate(raw: Any, segment_count: int) -> tuple[dict[str, Any], ...]:
    entries = raw.get("segments") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        raise ValueError("segments is not a list")
    answers: dict[int, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        index, name = entry.get("index"), entry.get("name")
        if isinstance(index, bool) or not isinstance(index, int) or not 1 <= index <= segment_count:
            continue
        if index in answers or not isinstance(name, str):
            continue
        name = " ".join(name.split())
        if not name or len(name) > MAX_NAME_CHARS or not _normalize(name):
            continue
        name = name[:1].upper() + name[1:]
        synonyms = entry.get("synonyms")
        terms = [name]
        seen = {_normalize(name)}
        for synonym in synonyms if isinstance(synonyms, list) else []:
            if not isinstance(synonym, str):
                continue
            synonym = " ".join(synonym.split())
            key = _normalize(synonym)
            if not key or len(synonym) > MAX_NAME_CHARS or key in seen:
                continue
            seen.add(key)
            terms.append(synonym)
            if len(terms) > MAX_SYNONYMS:
                break
        answers[index] = {"index": index, "name": name, "terms": terms}
    return tuple(answers[index] for index in sorted(answers))


# Ask one backend; raises _BackendFailure when it cannot give a valid answer.
def _ask(backend: str, texts: tuple[str, ...]) -> tuple[dict[str, Any], ...]:
    client = _client(backend)
    if not client.is_configured():
        raise _BackendFailure(NO_TOKEN)
    try:
        raw = client.complete_json(_system_prompt(), _user_message(texts), client.provider.max_output_tokens)
        return _validate(raw, len(texts))
    except AIUnavailable as exc:
        raise _BackendFailure(TIMEOUT if isinstance(exc.__cause__, httpx.TimeoutException) else ERROR) from exc
    except ValueError as exc:
        raise _BackendFailure(ERROR) from exc


# The answer of the first backend that gives a valid one, with its name. A
# backend that answers "nothing found" ends the search (no fallback for that);
# only a failure moves on to the next, and the last failure is raised when
# none answers. Successes are cached, failures are not (lru_cache keeps no exception).
@lru_cache(maxsize=CACHE_SIZE)
def _identify(backends: tuple[str, ...], texts: tuple[str, ...]) -> tuple[tuple[dict[str, Any], ...], str]:
    failure: _BackendFailure | None = None
    for backend in backends:
        try:
            return _ask(backend, texts), backend
        except _BackendFailure as exc:
            logger.warning("condition_ai_backend_failed backend=%s reason=%s", backend, exc.reason)
            failure = exc
    raise failure or _BackendFailure(DISABLED)


# Forget every cached answer (tests).
def clear_cache() -> None:
    _identify.cache_clear()


# The dictionary condition one of the terms of `terms` is exactly (name first,
# diacritics and case ignored), or None.
def _dictionary_condition(terms: list[str] | tuple[str, ...]) -> Condition | None:
    return conditions.load_dictionary().exact(terms)


# Identify the condition(s) the segments of `resolved` name by asking the AI
# backends. Never raises: every failure is a result with its reason.
def identify_conditions(resolved: ResolvedQuery) -> AIConditionResult:
    backends = settings.condition_ai_backends
    if not backends:
        return AIConditionResult(reason=DISABLED)
    texts = tuple(segment.text for segment in resolved.segments)
    if not texts:
        return AIConditionResult(reason=NONE)
    started = time.perf_counter()
    try:
        answers, backend = _identify(backends, texts)
    except _BackendFailure as failure:
        result = AIConditionResult(reason=failure.reason, backend=backends[-1])
    except Exception:
        logger.exception("condition_ai_unexpected_error")
        result = AIConditionResult(reason=ERROR)
    else:
        result = AIConditionResult(answers, backend, IDENTIFIED if answers else NONE)
    logger.info(
        "condition_ai_completed backend=%s reason=%s segments=%s identified=%s synonyms=%s mapped_to_dictionary=%s duration_ms=%s",
        result.backend or "-",
        result.reason,
        len(texts),
        ",".join(answer["name"] for answer in result.answers) or "-",
        ",".join(str(len(answer["terms"]) - 1) for answer in result.answers) or "-",
        ",".join("da" if _dictionary_condition(answer["terms"]) else "nu" for answer in result.answers) or "-",
        round((time.perf_counter() - started) * 1000),
    )
    return result


# Replace the segments the AI identified by whole-condition segments. When the
# name or a synonym is exactly a dictionary term, the condition takes that
# entry's canonical name (what the index carries for P1/P2) and keeps the AI's
# terms next to the entry's own; otherwise the AI's name stands as it is.
# Segments the AI did not name (or that already name a condition) stay as they are.
def with_ai_conditions(resolved: ResolvedQuery, answers: Any) -> ResolvedQuery:
    by_index = {
        answer["index"]: answer
        for answer in answers or ()
        if isinstance(answer, Mapping) and isinstance(answer.get("index"), int)
    }
    if not by_index:
        return resolved
    segments: list[QuerySegment] = []
    for position, segment in enumerate(resolved.segments, start=1):
        answer = by_index.get(position)
        if answer is None or segment.conditions:
            segments.append(segment)
            continue
        terms = [str(term) for term in answer["terms"]]
        known = _dictionary_condition(terms)
        if known is not None:
            name, merged = known.name, [*known.terms, *terms]
        else:
            name, merged = str(answer["name"]), terms
        unique: dict[str, str] = {}
        for term in merged:
            unique.setdefault(_normalize(term), term)
        condition = Condition(name, tuple(unique.values()))
        segments.append(QuerySegment(segment.text, (condition,), remainder="", whole_condition=True))
    return ResolvedQuery(tuple(segments))


# The message of a profile (a HealthProfile or its as_dict()) resolved against the
# dictionary, completed with the conditions the AI identified for it. The one
# resolution search, chat and PDF all use.
def resolved_for(profile: Any) -> ResolvedQuery:
    if isinstance(profile, Mapping):
        problem, answers = profile.get("health_problem"), profile.get("ai_conditions")
    else:
        problem, answers = getattr(profile, "health_problem", ""), getattr(profile, "ai_conditions", ())
    return with_ai_conditions(resolve_query(" ".join(str(problem or "").split())), answers)


# One throwaway request so the first patient does not wait for the local model
# to load. Only the local backend needs it; a failure is only logged.
def warm_up() -> None:
    if "local" not in settings.condition_ai_backends:
        return
    try:
        _ask("local", ("gripa",))
    except _BackendFailure as failure:
        logger.warning("condition_ai_warm_up_failed reason=%s", failure.reason)
