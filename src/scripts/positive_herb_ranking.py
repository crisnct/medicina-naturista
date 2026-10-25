"""Explicit, resumable positive-ranking stages used by the existing index CLI."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import replace
from uuid import uuid4

from backend.ai.herb_association_classification import (
    Work,
    cache_key,
    classification_prompt,
    group_fragment_works,
    make_client,
    model_digest,
    pack_batches,
    relation_id,
    semantic_config,
    serialize_batch,
    validate_cached,
    validate_response,
    verified_recommendation,
)
from backend.ai.herb_association_rules import (
    classify_rule,
    combine_fragment_decisions,
    content_hash,
    scoped_warning,
)
from backend.ai.herb_association_scope import LocalConditionScope
from backend.ai.herb_positive_repository import PositiveRepository
from backend.config import Settings
from backend.core.operation_context import OperationBudget, checkpoint, operation_budget


# Durations keep total hours rather than wrapping at a day boundary.
def _format_duration(seconds: float) -> str:
    hours, remainder = divmod(max(0, int(seconds)), 3600)
    minutes, seconds_part = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds_part:02d}"


# Only technical identifiers and aggregate counters reach the operator log.
def run_positive_ranking(
    settings: Settings,
    *,
    analyze: bool = False,
    publish: str | None = None,
    resume: str | None = None,
    repository: PositiveRepository | None = None,
) -> dict:
    repository = repository or PositiveRepository()
    started = time.monotonic()
    counters: dict = {"run_id": resume or str(uuid4()), "requests": 0, "completed": 0}
    stopped = threading.Event()

    def progress() -> None:
        elapsed = time.monotonic() - started
        done = counters["completed"]
        total = counters.get("batches", 0)
        rate = done / elapsed if elapsed else 0
        eta: str | None = None
        if rate:
            eta = _format_duration((total - done) / rate)
        print(
            json.dumps(
                {
                    **{key: value for key, value in counters.items() if key != "elapsed_seconds"},
                    "ai_requests_sent_total": counters["requests"],
                    "elapsed(hh:mm:ss)": _format_duration(elapsed),
                    "rate_batches_second": rate,
                    "ETA(hh:mm:ss)": eta,
                }
            ),
            flush=True,
        )

    def heartbeat() -> None:
        while not stopped.wait(60):
            progress()

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        with operation_budget(
            OperationBudget(
                started + settings.herb_association_build_timeout_seconds,
                time.monotonic,
                lambda: None,
            )
        ):
            if publish:
                repository.publish(publish, settings, digest=model_digest(settings))
                counters.update(run_id=publish, status="published")
                return counters
            data = repository.read_snapshot()
            scope_catalog = LocalConditionScope(data.conditions, data.condition_synonyms)
            semantic = semantic_config(settings)
            prompt = classification_prompt()
            if semantic_config(settings) != semantic:
                raise ValueError("POSITIVE_CONFIGURATION_CHANGED")
            digest = repository.analysis_digest(semantic) if analyze else model_digest(settings)
            rules, ambiguous = {}, []
            retained = {}
            groups = group_fragment_works(data.works, data.conditions)
            members = {relation_id(group.work): group.evidence for group in groups}
            data = replace(data, works=tuple(work for group in groups for work in group.evidence))
            for group in groups:
                checkpoint()
                work = group.work
                local = [classify_rule(*original) for original in group.originals]
                resolved = []
                for original, decision in zip(group.originals, local, strict=True):
                    warning = scoped_warning(*original)
                    for existing in (decision, warning):
                        if existing is not None:
                            resolved.append(
                                replace(
                                    existing,
                                    quotes=tuple(
                                        (a + original[0].start, b + original[0].start)
                                        for a, b in existing.quotes
                                    ),
                                )
                            )
                recommendation = verified_recommendation(
                    work,
                    condition_name=data.conditions[work[1].condition_id],
                    scope_catalog=scope_catalog,
                )
                if recommendation is not None:
                    resolved.append(recommendation)
                if any(decision is None for decision in local):
                    ambiguous.append(work)
                    retained[relation_id(work)] = resolved
                else:
                    decision = combine_fragment_decisions(resolved)
                    rules.update({relation_id(original): decision for original in group.evidence})
            keys = {
                relation_id(w): cache_key(
                    w,
                    {
                        **semantic,
                        "herb_name": data.names[w[1].herb_id],
                        "condition_name": data.conditions[w[1].condition_id],
                        "condition_synonyms": data.condition_synonyms.get(w[1].condition_id, ()),
                        "scope_catalog": data.manifest.get("conditions")
                        or content_hash([data.conditions, data.condition_synonyms]),
                    },
                    digest or "unverified",
                )
                for w in ambiguous
            }
            cached = repository.cached(list(keys.values())) if digest else {}
            # Cache stores offsets rather than quotations. Reject malformed or out-of-range entries.
            for work in ambiguous:
                cached_decision = cached.get(keys[relation_id(work)])
                if cached_decision is None:
                    continue
                validate_cached(cached_decision, work)
            unresolved: dict[str, Work] = {}
            for work in ambiguous:
                key = keys[relation_id(work)]
                if key not in cached:
                    unresolved.setdefault(key, work)
            batches = pack_batches(
                list(unresolved.values()),
                settings,
                data.names,
                data.conditions,
                condition_synonyms=data.condition_synonyms,
                prompt=prompt,
            )
            counters.update(
                units=len({u.identity for u, _ in data.works}),
                pairs=len(data.works),
                distinct_relations=len(groups),
                rules=len(rules),
                ambiguous=len(ambiguous),
                cache_hits=sum(
                    len(members[identifier]) for identifier, key in keys.items() if key in cached
                ),
                batches=len(batches),
                digest_verified=not analyze,
            )
            if analyze:
                counters.update(status="analyzed", model_digest=digest)
                return counters
            if len(batches) > settings.herb_association_ai_max_requests:
                raise ValueError("POSITIVE_REQUEST_LIMIT")
            assert digest is not None
            state = repository.create_run(counters["run_id"], data, semantic, digest, bool(resume))
            if state["status"] == "ready":
                counters["status"] = "ready"
                return counters
            client = make_client(settings) if batches else None
            try:
                for batch in batches:
                    assert client is not None
                    checkpoint()
                    payload = serialize_batch(
                        batch,
                        data.names,
                        data.conditions,
                        condition_synonyms=data.condition_synonyms,
                    )
                    repository.admit_request(
                        counters["run_id"], settings.herb_association_ai_max_requests
                    )
                    counters["requests"] += 1
                    raw = client.complete_json(
                        prompt,
                        payload,
                        settings.herb_association_ai_max_output_tokens,
                    )
                    checkpoint()
                    results = validate_response(
                        raw,
                        batch,
                        scope_catalog=scope_catalog,
                        max_passage_chars=settings.herb_association_ai_max_passage_chars,
                    )
                    entries = {
                        keys[identifier]: decision for identifier, decision in results.items()
                    }
                    repository.save_cache(entries)
                    cached.update(entries)
                    counters["completed"] += 1
            finally:
                if client is not None:
                    client.http.close()
            if semantic_config(settings) != semantic or classification_prompt() != prompt:
                raise ValueError("POSITIVE_CONFIGURATION_CHANGED")
            if model_digest(settings) != digest:
                raise ValueError("POSITIVE_MODEL_CHANGED")
            evidence_keys = {
                relation_id(original): key
                for identifier, key in keys.items()
                for original in members[identifier]
            }
            decisions = {
                **rules,
                **{
                    relation_id(original): combine_fragment_decisions(
                        [cached[key], *retained[identifier]]
                    )
                    for identifier, key in keys.items()
                    for original in members[identifier]
                },
            }
            counters["elapsed_seconds"] = round(time.monotonic() - started, 3)
            repository.finish(counters["run_id"], data, decisions, evidence_keys, counters)
            counters["status"] = "ready"
            return counters
    except Exception as error:
        counters.update(status="failed", error=type(error).__name__)
        raise
    finally:
        stopped.set()
        thread.join(timeout=1)
        progress()


# Keep the new generation inactive until preparation and all publication checks succeed.
def refresh_positive_ranking(settings: Settings) -> dict:
    run_positive_ranking(settings, analyze=True)
    prepared = run_positive_ranking(settings)
    published = run_positive_ranking(settings, publish=prepared["run_id"])
    # Publication sends no classification requests; retain the preparation total in the summary.
    published.update(
        requests=prepared["requests"],
        completed=prepared["completed"],
        ai_requests_sent_total=prepared["requests"],
    )
    print(json.dumps({"stage": "positive_ranking_summary", **published}), flush=True)
    return published
