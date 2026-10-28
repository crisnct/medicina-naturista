"""Explicit, resumable positive-ranking stages used by the existing index CLI."""

from __future__ import annotations

import threading
import time
from dataclasses import replace
from uuid import uuid4

from backend.ai.herb_association_classification import (
    Work,
    cache_key,
    classification_prompt,
    group_fragment_works,
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
from backend.ai.herb_caution_projection import model_projections
from backend.ai.herb_caution_repository import CautionRepository
from backend.ai.herb_positive_repository import PositiveRepository
from backend.ai.herb_product_safety_repository import ProductSafetyRepository
from backend.config import Settings
from backend.core.operation_context import OperationBudget, checkpoint, operation_budget
from scripts.herb_index_requests import emit_index_event, index_batch, make_client
from scripts.herb_product_safety_index import ProductSafetyCoordinator
from scripts.herb_safety_index import format_duration, workflow_progress


# Only technical identifiers and aggregate counters reach the operator log.
def run_positive_ranking(
    settings: Settings,
    *,
    analyze: bool = False,
    publish: str | None = None,
    resume: str | None = None,
    repository: PositiveRepository | None = None,
    caution_repository: CautionRepository | None = None,
    safety_repository: ProductSafetyRepository | None = None,
) -> dict:
    # Injected repositories stay hermetic unless the caller also supplies a caution adapter.
    if repository is None:
        repository = PositiveRepository()
        caution_repository = caution_repository or CautionRepository(repository.pool)
        safety_repository = safety_repository or ProductSafetyRepository(repository.pool)
    caution = caution_repository
    safety = safety_repository
    started = time.monotonic()
    counters: dict = {
        "run_id": resume or str(uuid4()),
        "requests": 0,
        "completed": 0,
        "progress_stage": "analysis",
    }
    safety_coordinator: ProductSafetyCoordinator | None = None
    stopped = threading.Event()

    def progress() -> None:
        elapsed = time.monotonic() - started
        warning_metrics = (
            safety_coordinator.progress_metrics() if safety_coordinator is not None else None
        )
        metrics = workflow_progress(counters, elapsed, warning_metrics)
        emit_index_event(
            {
                **{key: value for key, value in counters.items() if key != "elapsed_seconds"},
                "association_ai_requests": counters["requests"],
                "ai_requests_sent_total": counters["requests"]
                + counters.get("warnings_only_ai_requests", 0),
                "elapsed(hh:mm:ss)": format_duration(elapsed),
                **metrics,
            }
        )

    def heartbeat() -> None:
        while not stopped.wait(60):
            progress()

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        with operation_budget(
            OperationBudget(
                started
                + settings.herb_association_build_timeout_seconds
                + (settings.herb_safety_build_timeout_seconds if safety is not None else 0),
                time.monotonic,
                lambda: None,
            )
        ):
            if publish:
                counters["progress_stage"] = "publication"
                publication_digest = model_digest(settings)
                if caution is None:
                    repository.publish(publish, settings, digest=publication_digest)
                else:
                    caution_run = caution.prepared_for_positive(publish)
                    if caution_run is None:
                        caution_run = caution.prepare(publish, settings)["run_id"]
                    caution.publish(caution_run, settings, positive_digest=publication_digest)
                    counters["caution_run_id"] = caution_run
                if safety is not None and safety.is_ready(publish):
                    safety.publish(publish, settings, digest=publication_digest)
                    counters["safety_run_id"] = publish
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
            safety_coordinator = (
                ProductSafetyCoordinator(
                    settings,
                    safety,
                    counters["run_id"],
                    digest,
                    resume=bool(resume) or state["status"] == "ready",
                    counters=counters,
                )
                if safety is not None
                else None
            )
            if state["status"] == "ready":
                if caution is not None:
                    counters["progress_stage"] = "caution_preparation"
                    caution_run = caution.prepared_for_positive(counters["run_id"])
                    if caution_run is None:
                        caution_run = caution.prepare(counters["run_id"], settings)["run_id"]
                    counters["caution_run_id"] = caution_run
                if safety_coordinator is not None:
                    safety_coordinator.prepare(
                        client_factory=make_client, digest_verifier=model_digest
                    )
                counters["status"] = "ready"
                return counters
            counters["progress_stage"] = "associations"
            client = make_client(settings) if batches else None
            try:
                for number, batch in enumerate(batches, 1):
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
                    system = prompt
                    max_tokens = settings.herb_association_ai_max_output_tokens
                    with index_batch(
                        settings,
                        run_id=counters["run_id"],
                        kind="associations",
                        batch=number,
                        batches=len(batches),
                        system=system,
                        user=payload,
                        max_tokens=max_tokens,
                    ):
                        raw = client.complete_json(system, payload, max_tokens)
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
                        if caution is not None:
                            projected = model_projections(raw, batch, results)
                            caution.save_cache(
                                {keys[key]: value for key, value in projected.items()}
                            )
                    cached.update(entries)
                    counters["completed"] += 1
            finally:
                if client is not None:
                    client.http.close()
            counters["progress_stage"] = "ranking_preparation"
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
            if caution is not None:
                counters["progress_stage"] = "caution_preparation"
                projected_run = caution.prepare(counters["run_id"], settings)
                counters.update(
                    caution_run_id=projected_run["run_id"],
                    caution_unknown_count=projected_run["unknown_count"],
                )
            if safety_coordinator is not None:
                safety_coordinator.prepare(client_factory=make_client, digest_verifier=model_digest)
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
    published["warnings_only_ai_requests"] = prepared.get("warnings_only_ai_requests", 0)
    published["product_safety_ai_requests"] = prepared.get("product_safety_ai_requests", 0)
    published["ai_requests_sent_total"] += published["warnings_only_ai_requests"]
    emit_index_event({"stage": "positive_ranking_summary", **published})
    return published
