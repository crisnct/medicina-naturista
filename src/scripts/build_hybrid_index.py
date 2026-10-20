#!/usr/bin/env python3
"""Incrementally sync a traceable, local-only hybrid index for a Markdown
medical corpus into Postgres (pgvector for semantic search, tsvector for
lexical search). A document whose SHA-256 matches what's already stored is
skipped entirely — no re-chunking, no re-embedding, no DB write — so adding
or editing one document never touches the rest of the corpus."""

# Run like this:
#   .\.venv-gpu\Scripts\python src\scripts\build_hybrid_index.py
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import os
import re
import subprocess
import sys
import threading
import time
import traceback
import unicodedata
import uuid
from array import array
from collections.abc import Iterable, Mapping
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty
from typing import Callable, Iterator, Protocol, Sequence, TypedDict

import numpy as np

from backend.ai import db, herb_index_catalog, index_constants
from backend.ai.categories import ROOT_CATEGORY_ID
from backend.ai.condition_repository import FINGERPRINT_VERSION
from backend.ai.db import _embedding_dimension
from backend.ai.embedding_model import (
    DEFAULT_MODEL,
    EmbeddingProfile,
    create_embedding_model,
    get_profile,
)
from backend.ai.fragmenter import Fragment, fragment_document
from backend.ai.herb_index_catalog import fingerprint_rows
from backend.ai.herb_index_catalog import normalize_herb_name as _herb_text
from backend.ai.herb_index_catalog import read_index_catalogs as _herbs_catalogs
from backend.ai.herb_repository import HERBS_INDEX_VERSION, catalog_fingerprint, read_herbs
from backend.ai.index_state import (
    dictionary_snapshot,
    index_writer,
    passage_profile,
    read_metadata,
)
from backend.config import settings
from scripts.bootstrap_database import ensure_database
from scripts.migrate_database import migrate

# Minimum elapsed time between embedding progress messages.
PROGRESS_INTERVAL_SECONDS = 10.0
# Windows embedded per model call. 8 was the fastest on the GPU (fp16); larger
# batches only add padding and memory (see architecture/plan-migrare-qwen3-embedding.md).
BATCH_SIZE = 8
# Selected after corpus benchmarks of total publication time with 1/2/4/8 workers.
HERBS_INDEX_WORKERS = 2
# Lowest measured total time among the bounded fetch/COPY combinations.
HERBS_FETCH_SIZE = 2_000
HERBS_COPY_SIZE = 50_000
HERBS_TASK_TEXT_BYTES = 2 * 1024 * 1024
HERBS_TASK_RESULT_BYTES = 4 * 1024 * 1024
HERBS_IN_FLIGHT_BYTES = 128 * 1024 * 1024
HERBS_BITMAP_BUDGET_BYTES = 64 * 1024 * 1024
HERBS_WORKER_TIMEOUT_SECONDS = 120
HERBS_LOCK_TIMEOUT_MS = 60_000
HERBS_STATEMENT_TIMEOUT_MS = 600_000
_HERBS_TOKENS = herb_index_catalog.HERB_TOKENS
_HERBS_AUTOMATON = None
_HERBS_GATE = None
_BUILD_STAGE = "preparation"
HERBS_BENEFITS_DELETE_SQL = (
    "DELETE FROM herbs_benefits AS current WHERE NOT EXISTS ("
    "SELECT 1 FROM herbs_benefits_next AS next WHERE next.herb_id=current.herb_id "
    "AND next.medical_condition_id=current.medical_condition_id)"
)
HERBS_BENEFITS_INSERT_SQL = (
    "WITH existing AS MATERIALIZED (SELECT herb_id, medical_condition_id FROM herbs_benefits) "
    "INSERT INTO herbs_benefits (herb_id, medical_condition_id) "
    "SELECT next.herb_id, next.medical_condition_id FROM herbs_benefits_next AS next "
    "WHERE NOT EXISTS (SELECT 1 FROM existing AS current "
    "WHERE current.herb_id=next.herb_id AND current.medical_condition_id=next.medical_condition_id) "
    "ON CONFLICT (herb_id, medical_condition_id) DO NOTHING"
)


def _build_stage(stage: str) -> None:
    global _BUILD_STAGE
    _BUILD_STAGE = stage


def _safe_index_error(error: Exception) -> dict:
    detail = "".join(traceback.format_exception(error))
    for secret in (db.settings.database_url, settings.database_bootstrap_url):
        if secret:
            detail = detail.replace(secret, "[database connection]")
    detail = re.sub(r"postgres(?:ql)?://\S+", "[database connection]", detail)
    detail = re.sub(
        r"password\s*=\s*(?:'[^']*'|\S+)", "password=[redacted]", detail, flags=re.IGNORECASE
    )
    return dict(
        status="error",
        code="INDEX_SYNC_FAILED",
        stage=_BUILD_STAGE,
        type=type(error).__name__,
        traceback=detail,
    )


# Bumped whenever the text representation fed into embeddings/lexical search
# changes (e.g. the cleaning rules below), so build() forces a full resync
# even though every source file's own SHA-256 is unchanged. See build()'s use
# of TEXT_REPR_VERSION against sync_metadata.


@dataclass(frozen=True)
class HerbsIndexContext:
    condition_ids: tuple[int, ...]
    herb_ids: tuple[int, ...]
    condition_positions_by_term: Mapping[str, tuple[int, ...]]
    names: tuple[tuple[str, tuple[int, ...]], ...]
    conditions_fingerprint: str
    herbs_fingerprint: str
    previous_generation: str | None
    next_generation: str
    rebuild_required: bool
    reason: str
    row_count: int
    bitmap_bytes: int
    use_bitmaps: bool
    workers_required: bool


class HerbsIndexStats(TypedDict, total=False):
    chunks_read: int
    chunks_completed: int
    characters: int
    candidate_pairs: int
    staged_pairs: int
    row_count: int
    inserted: int
    deleted: int
    copy_batches: int
    normalization_seconds: float
    matching_seconds: float
    copy_seconds: float
    dedup_seconds: float
    publication_seconds: float
    scan_seconds: float
    elapsed_seconds: float
    peak_in_flight_bytes: int
    dedup: str
    reason: str


class EmbeddingModel(Protocol):
    def embed(
        self, documents: Iterable[str], *, batch_size: int, parallel: None
    ) -> Iterable[np.ndarray]: ...


def _herbs_bitmap_bytes(herbs: int, conditions: int) -> int:
    # Conservative CPython allocation: full-width ints, mappings and transient masks.
    digits = (conditions + sys.int_info.bits_per_digit - 1) // sys.int_info.bits_per_digit
    integer_bytes = sys.getsizeof(0) + digits * sys.int_info.sizeof_digit
    return (herbs + 2) * (integer_bytes + 8) + (herbs + conditions) * 128


def _prepare_herbs_index(
    connection,
    *,
    chunks_changed,
    previous_generation,
    next_generation,
    force_rebuild,
    bitmap_budget_bytes=None,
    no_eligible_work=False,
) -> HerbsIndexContext:
    started = time.monotonic()
    ids, herb_ids, terms, names, cf, hf = _herbs_catalogs(connection)
    if not connection.execute("SELECT to_regclass('herbs_benefits')").fetchone()[0]:
        raise RuntimeError("HERBS_BENEFITS_SCHEMA_MISSING: run database migrations")
    metadata = dict(connection.execute("SELECT key, value FROM sync_metadata").fetchall())
    row_count = connection.execute("SELECT count(*) FROM herbs_benefits").fetchone()[0]
    expected = {
        "herbs_benefits_index_version": str(HERBS_INDEX_VERSION),
        "herbs_benefits_chunks_generation": previous_generation,
        "herbs_benefits_conditions_fingerprint": cf,
        "herbs_benefits_herbs_fingerprint": hf,
        "herbs_benefits_row_count": str(row_count),
    }
    reason = (
        "forced"
        if force_rebuild
        else "chunks_changed"
        if chunks_changed
        else "metadata_changed"
        if not previous_generation or any(metadata.get(k) != v for k, v in expected.items())
        else "unchanged"
    )
    bitmap_bytes = _herbs_bitmap_bytes(len(herb_ids), len(ids))
    budget = HERBS_BITMAP_BUDGET_BYTES if bitmap_budget_bytes is None else bitmap_budget_bytes
    if budget < 0:
        raise ValueError("INVALID_HERBS_BITMAP_BUDGET")
    rebuild = reason != "unchanged"
    # Only skip workers when absence of eligible chunks is known after planned writes.
    workers_required = rebuild and not no_eligible_work
    if workers_required and not chunks_changed:
        workers_required = connection.execute(
            "SELECT EXISTS (SELECT 1 FROM chunks WHERE cardinality(primary_medical_conditions)>0)"
        ).fetchone()[0]
    print(
        f"herbs_benefits | preparation reason={reason} bitmap_bytes={bitmap_bytes} "
        f"dedup={'bitmaps' if bitmap_bytes <= budget else 'database'} "
        f"elapsed={time.monotonic() - started:.3f}s",
        flush=True,
    )
    return HerbsIndexContext(
        ids,
        herb_ids,
        terms,
        names,
        cf,
        hf,
        previous_generation,
        next_generation,
        rebuild,
        reason,
        row_count,
        bitmap_bytes,
        bitmap_bytes <= budget,
        workers_required,
    )


def _load_herbs_backend():
    try:
        import ahocorasick
    except ImportError as error:
        raise RuntimeError(
            "HERBS_MATCHER_UNAVAILABLE: install pyahocorasick in the indexer's Python environment: "
            f'{"& " if os.name == "nt" else ""}"{sys.executable}" '
            '-m pip install "pyahocorasick>=2.3.1,<3"'
        ) from error
    return ahocorasick


def _make_herbs_matcher(names):
    ahocorasick = _load_herbs_backend()

    automaton = ahocorasick.Automaton()
    for name, positions in names:
        automaton.add_word(name, (len(name), positions))
    automaton.make_automaton()
    return automaton


def _match_herbs(automaton, normalized: str) -> set[int]:
    found = set()
    for end, (length, positions) in automaton.iter(normalized):
        start = end - length + 1
        if (start == 0 or normalized[start - 1] == " ") and (
            end + 1 == len(normalized) or normalized[end + 1] == " "
        ):
            found.update(positions)
    return found


def _initialize_herbs_worker(names, readiness, gate) -> None:
    global _HERBS_AUTOMATON, _HERBS_GATE
    _HERBS_AUTOMATON = _make_herbs_matcher(names)
    _HERBS_GATE = gate
    readiness.put(os.getpid())


def _scan_herbs_batch(texts):
    offsets, positions = array("I", [0]), array("I")
    normalization_seconds = matching_seconds = 0.0
    for text in texts:
        started = time.monotonic()
        normalized = _herb_text(text)
        normalization_seconds += time.monotonic() - started
        started = time.monotonic()
        positions.extend(sorted(_match_herbs(_HERBS_AUTOMATON, normalized)))
        matching_seconds += time.monotonic() - started
        offsets.append(len(positions))
    return offsets, positions, normalization_seconds, matching_seconds


@contextmanager
def _prepared_herbs_workers(context):
    if not context.workers_required:
        yield None
        return
    started = time.monotonic()
    _build_stage("herbs_worker_preparation")
    # Spawned workers inherit this interpreter and its installed packages.
    _load_herbs_backend()
    spawn = multiprocessing.get_context("spawn")
    readiness, gate = spawn.Queue(), spawn.Event()
    executor = ProcessPoolExecutor(
        max_workers=HERBS_INDEX_WORKERS,
        mp_context=spawn,
        initializer=_initialize_herbs_worker,
        initargs=(context.names, readiness, gate),
    )
    try:
        # Blocking startup jobs ensure every worker initializes before publication.
        # The Event is shared through the initializer, not pickled as a task argument.
        startup = [executor.submit(_herbs_startup_job) for _ in range(HERBS_INDEX_WORKERS)]
        ready: set[int] = set()
        deadline = time.monotonic() + HERBS_WORKER_TIMEOUT_SECONDS
        last_report = started
        while len(ready) < HERBS_INDEX_WORKERS:
            for future in startup:
                if future.done():
                    future.result()
            try:
                ready.add(readiness.get(timeout=1))
            except Empty:
                if time.monotonic() >= deadline:
                    raise TimeoutError("HERBS_WORKER_INITIALIZATION_TIMEOUT")
            if time.monotonic() - last_report >= PROGRESS_INTERVAL_SECONDS:
                print(
                    f"herbs_benefits | preparing_workers ready={len(ready)}/{HERBS_INDEX_WORKERS} "
                    f"elapsed={format_duration(time.monotonic() - started)}",
                    flush=True,
                )
                last_report = time.monotonic()
        print(
            f"herbs_benefits | workers_ready={len(ready)} "
            f"elapsed={time.monotonic() - started:.3f}s",
            flush=True,
        )
        gate.set()
        for future in startup:
            future.result()
        yield executor
    finally:
        gate.set()
        executor.shutdown(wait=True, cancel_futures=True)
        readiness.close()
        readiness.join_thread()


def _herbs_startup_job():
    if _HERBS_GATE is None:
        raise RuntimeError("HERBS_WORKER_NOT_INITIALIZED")
    if not _HERBS_GATE.wait(HERBS_WORKER_TIMEOUT_SECONDS):
        raise TimeoutError("HERBS_WORKER_INITIALIZATION_TIMEOUT")
    return os.getpid()


def _herbs_condition_mask(context, primary) -> int:
    """Associate herbs only with the conditions named by the fragment's title."""
    mask = 0
    for term in set(primary):
        for position in context.condition_positions_by_term.get(term, ()):
            mask |= 1 << position
    return mask


def _new_herbs_pairs(context, seen, herb_positions, mask):
    for position in herb_positions:
        new = mask if seen is None else mask & ~seen[position]
        if seen is not None:
            seen[position] |= mask
        while new:
            lowest = new & -new
            yield context.herb_ids[position], context.condition_ids[lowest.bit_length() - 1]
            new ^= lowest


def _herbs_metadata(context, row_count):
    return {
        "herbs_benefits_index_version": str(HERBS_INDEX_VERSION),
        "herbs_benefits_chunks_generation": context.next_generation,
        "herbs_benefits_conditions_fingerprint": context.conditions_fingerprint,
        "herbs_benefits_herbs_fingerprint": context.herbs_fingerprint,
        "herbs_benefits_row_count": str(row_count),
    }


class HerbsProgress:
    def __init__(self, total, *, progress=print, clock=time.monotonic):
        self.total, self.progress, self.clock = total, progress, clock
        self.started = self.last = clock()
        self.last_completed = 0

    def report(self, stage, stats, *, active=0, force=False):
        now = self.clock()
        if not force and now - self.last < PROGRESS_INTERVAL_SECONDS:
            return
        elapsed = max(0.0, now - self.started)
        completed = stats["chunks_completed"]
        recent_elapsed = now - self.last
        rate = (
            (completed - self.last_completed) / recent_elapsed
            if recent_elapsed > 0
            else completed / elapsed
            if elapsed
            else 0
        )
        percent = 100 * completed / self.total if self.total else 100.0
        eta = format_duration((self.total - completed) / rate) if rate else "calculare"
        self.progress(
            f"herbs_benefits | {stage} {completed}/{self.total} ({percent:.2f}%) "
            f"read={stats['chunks_read']} active_tasks={active} "
            f"characters={stats['characters']} candidates={stats['candidate_pairs']} "
            f"rate={rate:.1f} chunks/s chars/s={stats['characters'] / max(elapsed, 1e-9):.1f} "
            f"elapsed={format_duration(elapsed)} ETA={eta}",
            flush=True,
        )
        self.last = now
        self.last_completed = completed


def _rebuild_herbs_benefits(
    connection, *, context, executor, progress=print, preserve_existing_ids=None
) -> HerbsIndexStats:
    """Caller owns connection, INDEX_LOCK, transaction and commit. Workers only scan text."""
    started = time.monotonic()
    _build_stage("herbs_scan_and_copy")
    total = connection.execute(
        "SELECT count(*) FROM chunks WHERE cardinality(primary_medical_conditions)>0"
    ).fetchone()[0]
    stats: HerbsIndexStats = dict(
        chunks_read=0,
        chunks_completed=0,
        characters=0,
        candidate_pairs=0,
        staged_pairs=0,
        row_count=0,
        inserted=0,
        deleted=0,
        copy_batches=0,
        normalization_seconds=0.0,
        matching_seconds=0.0,
        copy_seconds=0.0,
        dedup_seconds=0.0,
        publication_seconds=0.0,
        peak_in_flight_bytes=0,
        dedup="bitmaps" if context.use_bitmaps else "database",
    )
    reporter = HerbsProgress(total, progress=progress)
    reporter.report("scan_and_copy", stats, force=True)
    connection.execute(
        "CREATE TEMP TABLE herbs_benefits_raw "
        "(herb_id BIGINT, medical_condition_id BIGINT) ON COMMIT DROP"
    )
    seen = [0] * len(context.herb_ids) if context.use_bitmaps else None
    buffer: set[tuple[int, int]] = set()

    def flush():
        if not buffer:
            return
        tick = time.monotonic()
        with connection.cursor() as cursor:
            with cursor.copy(
                "COPY herbs_benefits_raw (herb_id, medical_condition_id) FROM STDIN"
            ) as copy:
                for pair in buffer:
                    copy.write_row(pair)
        stats["staged_pairs"] += len(buffer)
        stats["copy_batches"] += 1
        stats["copy_seconds"] += time.monotonic() - tick
        buffer.clear()

    active: dict[Future, tuple[list[int], list[int], int]] = {}
    in_flight_bytes = 0

    def collect(*, block):
        nonlocal in_flight_bytes
        done, _ = wait(active, timeout=1 if block else 0, return_when=FIRST_COMPLETED)
        for future in done:
            masks, sizes, cost = active.pop(future)
            in_flight_bytes -= cost
            offsets, positions, normalization, matching = future.result()
            stats["normalization_seconds"] += normalization
            stats["matching_seconds"] += matching
            for index, mask in enumerate(masks):
                found = positions[offsets[index] : offsets[index + 1]]
                stats["candidate_pairs"] += len(found) * mask.bit_count()
                for pair in _new_herbs_pairs(context, seen, found, mask):
                    buffer.add(pair)
                    if len(buffer) >= HERBS_COPY_SIZE:
                        flush()
                stats["chunks_completed"] += 1
                stats["characters"] += sizes[index]
        reporter.report("scan_and_copy", stats, active=len(active))

    def submit(texts, masks, sizes, text_bytes):
        nonlocal in_flight_bytes
        if not texts:
            return
        if executor is None:
            raise RuntimeError("HERBS_WORKERS_NOT_PREPARED")
        cost = (
            text_bytes
            + len(texts) * (len(context.herb_ids) * 4 + 4)
            + sum(sys.getsizeof(mask) for mask in masks)
        )
        # A single oversized fragment is processed intact and alone.
        while active and (
            len(active) >= 2 * HERBS_INDEX_WORKERS or in_flight_bytes + cost > HERBS_IN_FLIGHT_BYTES
        ):
            collect(block=True)
        future = executor.submit(_scan_herbs_batch, texts)
        active[future] = masks, sizes, cost
        in_flight_bytes += cost
        stats["peak_in_flight_bytes"] = max(stats["peak_in_flight_bytes"], in_flight_bytes)
        collect(block=False)

    try:
        with connection.cursor(name="herbs_benefits_scan") as cursor:
            cursor.itersize = HERBS_FETCH_SIZE
            cursor.execute(
                "SELECT chunk_id, text, primary_medical_conditions FROM chunks "
                "WHERE cardinality(primary_medical_conditions)>0"
            )
            texts: list[str] = []
            masks: list[int] = []
            sizes: list[int] = []
            text_bytes = 0
            for _, text, primary in cursor:
                stats["chunks_read"] += 1
                mask = _herbs_condition_mask(context, primary)
                if not mask:
                    stats["chunks_completed"] += 1
                    reporter.report("scan_and_copy", stats, active=len(active))
                    continue
                size = sys.getsizeof(text) + 4 * len(text)  # pickling and Unicode copies
                if texts and (
                    text_bytes + size > HERBS_TASK_TEXT_BYTES
                    or (len(texts) + 1) * (len(context.herb_ids) * 4 + 4) > HERBS_TASK_RESULT_BYTES
                ):
                    submit(texts, masks, sizes, text_bytes)
                    texts, masks, sizes, text_bytes = [], [], [], 0
                texts.append(text)
                masks.append(mask)
                sizes.append(len(text))
                text_bytes += size
            submit(texts, masks, sizes, text_bytes)
        while active:
            collect(block=True)
        flush()
    except BaseException:
        for future in active:
            future.cancel()
        raise
    stats["scan_seconds"] = time.monotonic() - started
    reporter.report("deduplication", stats, force=True)
    _build_stage("herbs_deduplication")
    tick = time.monotonic()
    if context.use_bitmaps:
        connection.execute("ALTER TABLE herbs_benefits_raw RENAME TO herbs_benefits_next")
    else:
        connection.execute(
            "CREATE TEMP TABLE herbs_benefits_next ON COMMIT DROP AS "
            "SELECT DISTINCT herb_id, medical_condition_id FROM herbs_benefits_raw"
        )
    connection.execute("CREATE UNIQUE INDEX ON herbs_benefits_next (herb_id, medical_condition_id)")
    connection.execute("ANALYZE herbs_benefits_next")
    stats["row_count"] = connection.execute("SELECT count(*) FROM herbs_benefits_next").fetchone()[
        0
    ]
    stats["dedup_seconds"] = time.monotonic() - tick
    # Association-only publication must never alter the indexed species' evidence.
    if preserve_existing_ids is not None:
        changed = connection.execute(
            "SELECT EXISTS ("
            "(SELECT herb_id,medical_condition_id FROM herbs_benefits_next WHERE herb_id=ANY(%s) "
            "EXCEPT SELECT herb_id,medical_condition_id FROM herbs_benefits) UNION ALL "
            "(SELECT herb_id,medical_condition_id FROM herbs_benefits EXCEPT "
            "SELECT herb_id,medical_condition_id FROM herbs_benefits_next)) OR EXISTS ("
            "SELECT FROM herbs h LEFT JOIN (SELECT herb_id,count(*) AS n "
            "FROM herbs_benefits_next GROUP BY herb_id) counts ON counts.herb_id=h.id "
            "WHERE h.id=ANY(%s) AND h.ranking IS DISTINCT FROM coalesce(counts.n,0))",
            (list(preserve_existing_ids), list(preserve_existing_ids)),
        ).fetchone()[0]
        if changed:
            raise RuntimeError("HERBS_ONLY_EXISTING_ASSOCIATIONS_CHANGED")
    reporter.report("publication_pending_commit", stats, force=True)
    _build_stage("herbs_publication")
    tick = time.monotonic()
    # Accurate target cardinality avoids poor anti-join plans after large changes.
    connection.execute("ANALYZE herbs_benefits")
    stats["deleted"] = connection.execute(HERBS_BENEFITS_DELETE_SQL).rowcount
    # Freeze the old pair set once, even when the INSERT target starts empty.
    stats["inserted"] = connection.execute(HERBS_BENEFITS_INSERT_SQL).rowcount
    # Publish the derived ranking with the new associations, including zero counts.
    connection.execute(
        "UPDATE herbs AS h SET ranking = counts.total_conditions FROM ("
        "SELECT herb.id AS herb_id, COUNT(DISTINCT hb.medical_condition_id) AS total_conditions "
        "FROM herbs AS herb LEFT JOIN herbs_benefits AS hb ON hb.herb_id=herb.id "
        "GROUP BY herb.id) AS counts "
        "WHERE h.id=counts.herb_id AND h.ranking IS DISTINCT FROM counts.total_conditions"
    )
    stats["publication_seconds"] = time.monotonic() - tick
    stats["elapsed_seconds"] = time.monotonic() - started
    return stats


# Recover the previous indexed prefix from its fingerprint, rather than guessing
# that every zero-ranking row is new. Changed/removed old names fail closed.
def _indexed_herb_ids(context: HerbsIndexContext, fingerprint: str) -> tuple[int, ...]:
    names: list[list[str]] = [[] for _ in context.herb_ids]
    for name, positions in context.names:
        for position in positions:
            names[position].append(name)
    rows = [
        [identifier, sorted(names[position])]
        for position, identifier in enumerate(context.herb_ids)
    ]
    for length in range(len(rows), 0, -1):
        if fingerprint_rows(rows[:length]) == fingerprint:
            return context.herb_ids[:length]
    raise RuntimeError("HERBS_ONLY_EXISTING_CATALOG_CHANGED")


def rebuild_herbs_only() -> HerbsIndexStats:
    """Refresh derived associations on an existing compatible index, without corpus I/O."""
    _build_stage("index_lock")
    with index_writer(lock_timeout_ms=HERBS_LOCK_TIMEOUT_MS) as connection:
        connection.execute(
            "SELECT set_config('statement_timeout', %s, false)",
            (str(HERBS_STATEMENT_TIMEOUT_MS),),
        )
        metadata = read_metadata(connection)
        stored = dict(connection.execute("SELECT key,value FROM sync_metadata").fetchall())
        context = _prepare_herbs_index(
            connection,
            chunks_changed=False,
            previous_generation=metadata.index_generation,
            next_generation=metadata.index_generation,
            force_rebuild=True,
        )
        catalog_state = catalog_fingerprint(read_herbs(connection))
        expected = {
            "herbs_benefits_index_version": str(HERBS_INDEX_VERSION),
            "herbs_benefits_chunks_generation": metadata.index_generation,
            "herbs_benefits_conditions_fingerprint": context.conditions_fingerprint,
            "herbs_benefits_row_count": str(context.row_count),
        }
        if any(stored.get(key) != value for key, value in expected.items()):
            raise RuntimeError("HERBS_ONLY_INCOMPATIBLE_ASSOCIATIONS")
        indexed_ids = _indexed_herb_ids(context, stored.get("herbs_benefits_herbs_fingerprint", ""))
        with _prepared_herbs_workers(context) as executor, connection.transaction():
            # Raw SQL writers must not change the snapshots while workers scan them.
            connection.execute(
                "LOCK TABLE documents,chunks,herbs,herb_aliases,medical_conditions,"
                "medical_condition_synonyms,herbs_benefits,sync_metadata IN SHARE MODE"
            )
            if (
                read_metadata(connection) != metadata
                or dict(connection.execute("SELECT key,value FROM sync_metadata").fetchall())
                != stored
                or _herbs_catalogs(connection)[-2:]
                != (context.conditions_fingerprint, context.herbs_fingerprint)
                or catalog_fingerprint(read_herbs(connection)) != catalog_state
            ):
                raise RuntimeError("HERBS_CATALOG_CHANGED_DURING_BUILD")
            stats = _rebuild_herbs_benefits(
                connection,
                context=context,
                executor=executor,
                preserve_existing_ids=indexed_ids,
            )
            for key, value in _herbs_metadata(context, stats["row_count"]).items():
                connection.execute(
                    "INSERT INTO sync_metadata(key,value) VALUES(%s,%s) "
                    "ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value "
                    "WHERE sync_metadata.value IS DISTINCT FROM EXCLUDED.value",
                    (key, value),
                )
            _build_stage("commit")
    print(json.dumps({"status": "ok", "mode": "herbs_only", "herbs_benefits": stats}), flush=True)
    return stats


class GPUUsageMonitor:
    """Read GPU 0's GPU-Util column without blocking the embedding loop."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._process: subprocess.Popen | None = None
        self._thread = threading.Thread(target=self._run, name="gpu-usage", daemon=True)
        self._usage: int | None = None
        self._updated = 0.0
        self._gpu: int | None = None

    def __enter__(self) -> GPUUsageMonitor:
        self._thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._stop.set()
        with self._lock:
            process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        self._thread.join(timeout=3)

    def percent(self) -> str:
        with self._lock:
            if self._usage is None or time.monotonic() - self._updated > 3:
                return "N/A"
            return f"{self._usage}%"

    def _consume(self, line: str) -> None:
        gpu = re.match(r"^\|\s*(\d+)\s+", line)
        if gpu:
            self._gpu = int(gpu[1])
        columns = line.split("|")
        if self._gpu != 0 or len(columns) < 5 or "MiB" not in columns[2]:
            return
        usage = re.match(r"\s*(\d{1,3})%", columns[3])
        if usage and int(usage[1]) <= 100:
            with self._lock:
                self._usage = int(usage[1])
                self._updated = time.monotonic()

    def _run(self) -> None:
        try:
            with self._lock:
                if self._stop.is_set():
                    return
                self._process = subprocess.Popen(
                    ["nvidia-smi", "--loop=1"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                process = self._process
            assert process.stdout is not None
            try:
                for line in process.stdout:
                    if self._stop.is_set():
                        break
                    self._consume(line)
            finally:
                process.stdout.close()
        except OSError:
            # GPU monitoring is optional, including on machines without NVIDIA.
            pass
        finally:
            with self._lock:
                self._usage = None


@dataclass(frozen=True)
class SourceFile:
    relative_path: str
    absolute_path: str
    size_bytes: int
    modified_utc: str
    sha256: str
    encoding: str
    line_count: int
    char_count: int
    # The document's category: its containing folder's path relative to the
    # source root (posix-separated), or ROOT_CATEGORY_ID when the file sits
    # directly in the source root.
    category_id: str = ROOT_CATEGORY_ID


@dataclass(frozen=True)
class Chunk:
    source_relative_path: str
    source_absolute_path: str
    source_sha256: str
    line_start: int
    line_end: int
    heading: str
    text: str
    text_sha256: str
    char_count: int
    # Inherited from the source document's category_id (see SourceFile).
    category_id: str = ROOT_CATEGORY_ID
    # Set by ai/fragmenter.py: R1/R2/D1, and the conditions named in the
    # fragment's title / in its text (empty for D1).
    business_category: str = "D1"
    primary_medical_conditions: tuple[str, ...] = ()
    secondary_medical_conditions: tuple[str, ...] = ()


# Return the current UTC timestamp in a stable ISO-8601 representation.
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# Compute the SHA-256 digest of an in-memory byte sequence.
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# Compute a file digest incrementally to keep memory usage bounded. Used as
# the cheap "did this document change?" check before deciding whether to
# read/chunk/embed it at all.
def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(block_size):
            digest.update(block)
    return digest.hexdigest()


# Read a Markdown file using the supported encodings and return raw bytes as well.
def read_markdown(path: Path) -> tuple[str, str, bytes]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1250", "cp1252"):
        try:
            return raw.decode(encoding), encoding, raw
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8-replace", raw


# Normalize null characters and line endings before indexing source text.
def normalize_text(text: str) -> str:
    normalized = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    return unicodedata.normalize("NFC", normalized)


# The source/category/heading context line prepended to a chunk's own text
# before embedding it.
def _embedding_context(chunk: Chunk) -> str:
    lines = []
    if chunk.category_id:
        lines.append(chunk.category_id.replace("/", " > "))
    lines.append(Path(chunk.source_relative_path).stem)
    if chunk.heading:
        lines.append(chunk.heading)
    return "\n".join(lines)


# Model inputs for one chunk: its context line plus the passage text, written as
# the model's profile wants a passage. A passage longer than profile.max_chars is
# cut into overlapping windows, so the model does not silently truncate it and
# drop the tail; the windows' vectors are averaged back into one by embed_chunks().
def _embedding_windows(chunk: Chunk, profile: EmbeddingProfile) -> list[str]:
    context = _embedding_context(chunk)
    text = chunk.text
    step = profile.max_chars - profile.overlap_chars
    windows = []
    position = 0
    while True:
        window = text[position : position + profile.max_chars]
        windows.append(profile.passage_text(f"{context}\n{window}"))
        if position + profile.max_chars >= len(text):
            return windows
        position += step


# Convert chunks into model inputs, one per embedding window.
def iter_embedding_inputs(chunks: Sequence[Chunk], profile: EmbeddingProfile) -> Iterator[str]:
    for chunk in chunks:
        yield from _embedding_windows(chunk, profile)


# Format elapsed and estimated durations as stable terminal-friendly timestamps.
def format_duration(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


# Generate, validate, and normalize embeddings while reporting measured
# progress. Progress counts windows (see _embedding_windows()): almost every
# fragment is longer than one window, so this is the real amount of work.
def embed_chunks(
    model: EmbeddingModel,
    chunks: Sequence[Chunk],
    batch_size: int,
    profile: EmbeddingProfile,
    *,
    progress_interval_seconds: float = PROGRESS_INTERVAL_SECONDS,
    clock: Callable[[], float] | None = None,
    gpu_usage: Callable[[], str] | None = None,
) -> np.ndarray:
    if progress_interval_seconds <= 0:
        raise ValueError("Progress interval must be greater than zero")

    monotonic = clock or time.monotonic
    total = len(chunks)
    inputs: list[str] = []
    owners: list[int] = []  # index of the chunk each window belongs to
    for index, chunk in enumerate(chunks):
        windows = _embedding_windows(chunk, profile)
        inputs += windows
        owners += [index] * len(windows)
    window_total = len(inputs)

    vectors: list[np.ndarray] = []
    started = monotonic()
    last_report = started

    for processed, vector in enumerate(
        model.embed(inputs, batch_size=batch_size, parallel=None), start=1
    ):
        vectors.append(vector)
        now = monotonic()
        if processed < window_total and now - last_report >= progress_interval_seconds:
            elapsed = max(now - started, 1e-9)
            rate = processed / elapsed
            eta = (window_total - processed) / rate if rate > 0 else 0.0
            percent = processed * 100.0 / window_total
            print(
                f"Embedding progress: {processed}/{window_total} ({percent:.1f}%) | "
                f"elapsed {format_duration(elapsed)} | rate {rate:.1f} windows/s | "
                f"ETA {format_duration(eta)} | GPU usage: {gpu_usage() if gpu_usage else 'N/A'}",
                flush=True,
            )
            last_report = now

    window_embeddings = np.asarray(vectors, dtype=np.float32)
    if window_total and window_embeddings.shape != (window_total, profile.dimension):
        raise RuntimeError(f"Unexpected embedding matrix shape: {window_embeddings.shape}")
    embeddings = np.zeros((total, profile.dimension), dtype=np.float32)
    if window_total:
        norms = np.linalg.norm(window_embeddings, axis=1)
        if not np.isfinite(window_embeddings).all() or np.any(norms == 0):
            raise RuntimeError("Embedding matrix contains non-finite or zero vectors")
        window_embeddings /= norms[:, None]
        # A chunk's vector is the re-normalized mean of its windows' vectors.
        np.add.at(embeddings, np.asarray(owners), window_embeddings)
        chunk_norms = np.linalg.norm(embeddings, axis=1)
        if not np.isfinite(chunk_norms).all() or np.any(chunk_norms == 0):
            raise RuntimeError("Windowed embedding produced a non-finite or zero vector")
        embeddings /= chunk_norms[:, None]

    elapsed = monotonic() - started
    rate = window_total / max(elapsed, 1e-9)
    print(
        f"Embedding completed: {total}/{total} (100.0%) | windows {window_total} | "
        f"elapsed {format_duration(elapsed)} | rate {rate:.1f} windows/s",
        flush=True,
    )
    return embeddings


# The lexical text_search column indexes the same three fields the old
# SQLite FTS5 virtual table did (text, heading, source path) — see
# ai/search.py's lexical query for how it's matched against.
def _text_search_input(chunk: Chunk) -> str:
    return f"{chunk.text} {chunk.heading} {chunk.source_relative_path}"


# Replace one document inside the caller-owned publication transaction.
def _write_document(
    connection, source: SourceFile, chunks: Sequence[Chunk], embeddings: np.ndarray
) -> None:
    # category_id is not written here: it's a GENERATED column in Postgres,
    # always derived from relative_path/source_relative_path (see db.py's
    # SCHEMA_SQL) — Python still computes it (SourceFile/Chunk.category_id)
    # because iter_embedding_inputs() needs it in the passage text before
    # this function ever runs.
    connection.execute(
        "DELETE FROM chunks WHERE source_relative_path = %s", (source.relative_path,)
    )
    connection.execute(
        """
        INSERT INTO documents
            (relative_path, absolute_path, size_bytes, modified_utc, sha256, encoding, line_count, char_count)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (relative_path) DO UPDATE SET
            absolute_path = EXCLUDED.absolute_path,
            size_bytes = EXCLUDED.size_bytes,
            modified_utc = EXCLUDED.modified_utc,
            sha256 = EXCLUDED.sha256,
            encoding = EXCLUDED.encoding,
            line_count = EXCLUDED.line_count,
            char_count = EXCLUDED.char_count
        """,
        (
            source.relative_path,
            source.absolute_path,
            source.size_bytes,
            source.modified_utc,
            source.sha256,
            source.encoding,
            source.line_count,
            source.char_count,
        ),
    )
    for chunk, embedding in zip(chunks, embeddings):
        connection.execute(
            """
            INSERT INTO chunks
                (source_relative_path, source_absolute_path, source_sha256, line_start, line_end,
                 heading, text, text_sha256, char_count, embedding, text_search,
                 business_category, primary_medical_conditions, secondary_medical_conditions)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, to_tsvector('simple', unaccent(%s)), %s,%s,%s)
            """,
            (
                chunk.source_relative_path,
                chunk.source_absolute_path,
                chunk.source_sha256,
                chunk.line_start,
                chunk.line_end,
                chunk.heading,
                chunk.text,
                chunk.text_sha256,
                chunk.char_count,
                embedding,
                _text_search_input(chunk),
                chunk.business_category,
                list(chunk.primary_medical_conditions),
                list(chunk.secondary_medical_conditions),
            ),
        )


# Sync medicina-naturista-documente/data/documents into Postgres: unchanged files (same SHA-256 already
# stored) are skipped entirely; new/changed files are re-chunked, re-embedded,
# and published together in one transaction; files removed from source are deleted.
def build(
    source: Path, model_name: str, batch_size: int = BATCH_SIZE, *, rebuild_herbs: bool = False
) -> None:
    if batch_size <= 0:
        raise ValueError("INVALID_BATCH_SIZE")
    source = source.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Source directory does not exist: {source}")
    get_profile(model_name)
    _build_stage("database_bootstrap")
    created = ensure_database(db.settings.database_url, settings.database_bootstrap_url)
    _build_stage("migrations")
    versions = migrate(db.settings.database_url, lock_timeout_ms=HERBS_LOCK_TIMEOUT_MS)
    print(
        json.dumps({"stage": "database_ready", "created": created, "migrations": versions}),
        flush=True,
    )
    with GPUUsageMonitor() as monitor:
        _build_stage("index_lock")
        with index_writer(lock_timeout_ms=HERBS_LOCK_TIMEOUT_MS) as connection:
            connection.execute(
                "SELECT set_config('statement_timeout', %s, false)",
                (str(HERBS_STATEMENT_TIMEOUT_MS),),
            )
            _build(
                source,
                model_name,
                batch_size,
                gpu_usage=monitor.percent,
                connection=connection,
                rebuild_herbs=rebuild_herbs,
            )


def _build(
    source: Path,
    model_name: str,
    batch_size: int,
    *,
    gpu_usage: Callable[[], str],
    connection,
    rebuild_herbs: bool = False,
) -> None:
    if batch_size <= 0:
        raise ValueError("INVALID_BATCH_SIZE")
    source = source.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Source directory does not exist: {source}")

    profile = get_profile(model_name)
    _build_stage("fragmentation")
    settings.model_cache_dir.mkdir(parents=True, exist_ok=True)
    fingerprint, dictionary = dictionary_snapshot(connection)

    def traversal_error(error):
        raise error

    paths = sorted(
        (
            Path(root, name)
            for root, _directories, names in os.walk(source, onerror=traversal_error)
            for name in names
            if name.casefold().endswith(".md")
        ),
        key=lambda item: item.relative_to(source).as_posix().casefold(),
    )
    if not paths:
        raise RuntimeError(f"No Markdown files found in {source}")

    existing = dict(connection.execute("SELECT relative_path, sha256 FROM documents").fetchall())
    stored = dict(connection.execute("SELECT key, value FROM sync_metadata").fetchall())
    stored_paths = set(existing)
    expected = {
        "model_name": model_name,
        "model_dimension": str(profile.dimension),
        "dictionary_fingerprint": fingerprint,
        "dictionary_fingerprint_version": str(FINGERPRINT_VERSION),
        "passage_profile": passage_profile(profile),
        "text_repr_version": index_constants.TEXT_REPR_VERSION,
    }
    if _embedding_dimension(connection) != profile.dimension or any(
        stored.get(key) != value for key, value in expected.items()
    ):
        existing = {}

    warnings: list[str] = []
    skipped = 0
    pending: list[tuple[SourceFile, list[Fragment]]] = []
    all_new_chunks: list[Chunk] = []
    initial_stats: dict[str, tuple[int, int]] = {}
    source_hashes: dict[str, str] = {}

    def report_progress(index: int) -> None:
        if index % 50 == 0 or index == len(paths):
            print(
                f"Scanned {index}/{len(paths)} files; {len(pending)} changed, {skipped} unchanged",
                flush=True,
            )

    for index, path in enumerate(paths, start=1):
        relative = path.relative_to(source).as_posix()
        category_id = path.parent.relative_to(source).as_posix()
        if category_id == ".":
            category_id = ROOT_CATEGORY_ID
        file_hash = sha256_file(path)
        source_hashes[relative] = file_hash
        if existing.get(relative) == file_hash:
            skipped += 1
            report_progress(index)
            continue

        stat = path.stat()
        initial_stats[relative] = (stat.st_size, stat.st_mtime_ns)
        decoded, encoding, raw = read_markdown(path)
        # Sources are expected to already be clean (see scripts/clean_documents.py,
        # which strips external links and "Vezi și" references from files on
        # disk) — this only normalizes line endings/unicode form.
        normalized = normalize_text(decoded)
        if encoding == "utf-8-replace":
            warnings.append(f"Replacement characters used while decoding: {relative}")
        source_hash = sha256_bytes(raw)
        if source_hash != file_hash:
            raise RuntimeError(f"Hash mismatch while reading {relative} (file changed during sync)")
        source_file = SourceFile(
            relative_path=relative,
            absolute_path=str(path),
            size_bytes=len(raw),
            modified_utc=datetime.fromtimestamp(stat.st_mtime, timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            sha256=source_hash,
            encoding=encoding,
            line_count=normalized.count("\n") + 1,
            char_count=len(normalized),
            category_id=category_id,
        )
        document_chunks = fragment_document(normalized, dictionary)
        if not document_chunks:
            warnings.append(f"No indexable text: {relative}")
        pending.append((source_file, document_chunks))
        for fragment in document_chunks:
            all_new_chunks.append(
                Chunk(
                    source_relative_path=relative,
                    source_absolute_path=str(path),
                    source_sha256=source_hash,
                    line_start=fragment.line_start,
                    line_end=fragment.line_end,
                    heading=fragment.path,
                    text=fragment.text,
                    text_sha256=sha256_bytes(fragment.text.encode("utf-8")),
                    char_count=len(fragment.text),
                    category_id=category_id,
                    business_category=fragment.business_category.value,
                    primary_medical_conditions=fragment.primary_conditions,
                    secondary_medical_conditions=fragment.secondary_conditions,
                )
            )
        report_progress(index)

    embeddings = np.empty((0, profile.dimension), dtype=np.float32)
    if all_new_chunks:
        _build_stage("embeddings")
        print(
            f"Loading local embedding model {model_name} (device {settings.embedding_device})",
            flush=True,
        )
        model = create_embedding_model(model_name, settings.model_cache_dir)
        print(
            f"Embedding {len(all_new_chunks)} chunks from {len(pending)} changed files (batch size {batch_size})",
            flush=True,
        )
        embeddings = embed_chunks(model, all_new_chunks, batch_size, profile, gpu_usage=gpu_usage)

        changed_during_sync = []
        for relative, (size, mtime_ns) in initial_stats.items():
            current = Path(source, relative).stat()
            if (current.st_size, current.st_mtime_ns) != (size, mtime_ns):
                changed_during_sync.append(relative)
        if changed_during_sync:
            raise RuntimeError(
                "Source files changed during sync: " + ", ".join(changed_during_sync[:10])
            )

    if (
        embeddings.shape != (len(all_new_chunks), profile.dimension)
        or not np.isfinite(embeddings).all()
    ):
        raise RuntimeError("INVALID_EMBEDDINGS")
    if all_new_chunks and np.any(np.linalg.norm(embeddings, axis=1) == 0):
        raise RuntimeError("INVALID_EMBEDDINGS")
    for relative, digest in source_hashes.items():
        if sha256_file(source / relative) != digest:
            raise RuntimeError("CORPUS_CHANGED_DURING_BUILD")
    current_relative_paths = {path.relative_to(source).as_posix() for path in paths}
    removed = sorted(stored_paths - current_relative_paths)
    # Recheck the DB catalog before publication; all writers follow INDEX_LOCK.
    if dictionary_snapshot(connection)[0] != fingerprint:
        raise RuntimeError("DICTIONARY_CHANGED_DURING_BUILD")
    next_generation = str(uuid.uuid4())
    dimension_changed = _embedding_dimension(connection) != profile.dimension
    # A planned complete replacement with no eligible fragments needs no CPU pool.
    retained_eligible = (
        connection.execute(
            "SELECT EXISTS (SELECT 1 FROM chunks WHERE NOT (source_relative_path=ANY(%s)) "
            "AND cardinality(primary_medical_conditions)>0)",
            ([item.relative_path for item, _ in pending] + removed,),
        ).fetchone()[0]
        if not dimension_changed
        else False
    )
    no_eligible_work = not retained_eligible and not any(
        item.primary_medical_conditions for item in all_new_chunks
    )
    context = _prepare_herbs_index(
        connection,
        chunks_changed=bool(pending or removed or dimension_changed),
        previous_generation=stored.get("index_generation"),
        next_generation=next_generation,
        force_rebuild=rebuild_herbs,
        no_eligible_work=no_eligible_work,
    )
    with _prepared_herbs_workers(context) as executor:
        # Repeat final validation after worker startup, immediately before publication.
        for relative, digest in source_hashes.items():
            if sha256_file(source / relative) != digest:
                raise RuntimeError("CORPUS_CHANGED_DURING_BUILD")
        if dictionary_snapshot(connection)[0] != fingerprint:
            raise RuntimeError("DICTIONARY_CHANGED_DURING_BUILD")
        if _herbs_catalogs(connection)[-2:] != (
            context.conditions_fingerprint,
            context.herbs_fingerprint,
        ):
            raise RuntimeError("HERBS_CATALOG_CHANGED_DURING_BUILD")
        with connection.transaction():
            _build_stage("chunks_publication")
            if _embedding_dimension(connection) != profile.dimension:
                connection.execute("DELETE FROM documents")
                connection.execute("ALTER TABLE chunks DROP COLUMN embedding")
                connection.execute(
                    f"ALTER TABLE chunks ADD COLUMN embedding vector({profile.dimension}) NOT NULL"
                )
            offset = 0
            for source_file, document_chunks in pending:
                count = len(document_chunks)
                _write_document(
                    connection,
                    source_file,
                    all_new_chunks[offset : offset + count],
                    embeddings[offset : offset + count],
                )
                offset += count
            if removed:
                connection.execute(
                    "DELETE FROM documents WHERE relative_path = ANY(%s)", (removed,)
                )
            if dictionary_snapshot(connection)[0] != fingerprint:
                raise RuntimeError("DICTIONARY_CHANGED_DURING_BUILD")
            herbs_stats = (
                _rebuild_herbs_benefits(connection, context=context, executor=executor)
                if context.rebuild_required
                else dict(row_count=context.row_count, inserted=0, deleted=0, reason="unchanged")
            )
            metadata = {
                **expected,
                "last_synced_utc": utc_now(),
                "index_generation": next_generation,
                **_herbs_metadata(context, herbs_stats["row_count"]),
            }
            for key, value in metadata.items():
                connection.execute(
                    "INSERT INTO sync_metadata (key, value) VALUES (%s, %s) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                    (key, value),
                )
            _build_stage("commit")

    print(
        json.dumps(
            {
                "status": "ok",
                "files_scanned": len(paths),
                "files_unchanged": skipped,
                "files_synced": len(pending),
                "files_removed": len(removed),
                "chunks_written": len(all_new_chunks),
                "warnings": len(warnings),
                "herbs_benefits": herbs_stats,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


# Parse command-line options for the incremental index sync.
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=settings.documents_dir)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--rebuild-herbs",
        action="store_true",
        help="Force rebuilding herb/condition associations without re-embedding unchanged documents",
    )
    modes.add_argument(
        "--rebuild-herbs-only",
        action="store_true",
        help="Refresh associations only; requires a compatible existing index and preserves old pairs",
    )
    return parser.parse_args()


if __name__ == "__main__":
    from backend.config import Settings, configure_settings

    configure_settings(Settings.from_env(dotenv=True))
    arguments = parse_args()
    try:
        if arguments.rebuild_herbs_only:
            rebuild_herbs_only()
        else:
            build(arguments.source, arguments.model, rebuild_herbs=arguments.rebuild_herbs)
    except Exception as exc:
        print(
            json.dumps(_safe_index_error(exc), ensure_ascii=False),
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)
