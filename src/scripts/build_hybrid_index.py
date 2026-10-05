#!/usr/bin/env python3
"""Incrementally sync a traceable, local-only hybrid index for a Markdown
medical corpus into Postgres (pgvector for semantic search, tsvector for
lexical search). A document whose SHA-256 matches what's already stored is
skipped entirely — no re-chunking, no re-embedding, no DB write — so adding
or editing one document never touches the rest of the corpus."""
# Run like this:
# .\.venv-gpu\Scripts\python scripts\build_hybrid_index.py
# Monitor GPU cuda usage
# nvidia-smi --loop=3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Sequence

import numpy as np
from psycopg.rows import namedtuple_row

from backend.ai.categories import ROOT_CATEGORY_ID
from backend.ai.conditions import load_dictionary
from backend.ai.db import ensure_schema, get_pool
from backend.ai.embedding_model import (
    DEFAULT_MODEL,
    EmbeddingProfile,
    create_embedding_model,
    get_profile,
)
from backend.ai.fragmenter import Fragment, fragment_document
from backend.config import settings

# Minimum elapsed time between embedding progress messages.
PROGRESS_INTERVAL_SECONDS = 10.0
# Windows embedded per model call. 8 was the fastest on the GPU (fp16); larger
# batches only add padding and memory (see architecture/plan-migrare-qwen3-embedding.md).
BATCH_SIZE = 8

# Bumped whenever the text representation fed into embeddings/lexical search
# changes (e.g. the cleaning rules below), so build() forces a full resync
# even though every source file's own SHA-256 is unchanged. See build()'s use
# of TEXT_REPR_VERSION against sync_metadata.
TEXT_REPR_VERSION = "6"


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
        window = text[position:position + profile.max_chars]
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
    model: object,
    chunks: Sequence[Chunk],
    batch_size: int,
    profile: EmbeddingProfile,
    *,
    progress_interval_seconds: float = PROGRESS_INTERVAL_SECONDS,
    clock: Callable[[], float] | None = None,
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

    for processed, vector in enumerate(model.embed(inputs, batch_size=batch_size, parallel=None), start=1):
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
                f"ETA {format_duration(eta)}",
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


# Replace a document's chunks and upsert its row. Called with a connection
# freshly acquired from the pool for this one document (see build()), so the
# pool's own commit-on-exit/rollback-on-exception makes this a single
# transaction — a reader never sees a document with only some of its new
# chunks written, and one document's write never rolls back another's.
def _write_document(connection, source: SourceFile, chunks: Sequence[Chunk], embeddings: np.ndarray) -> None:
    # category_id is not written here: it's a GENERATED column in Postgres,
    # always derived from relative_path/source_relative_path (see db.py's
    # SCHEMA_SQL) — Python still computes it (SourceFile/Chunk.category_id)
    # because iter_embedding_inputs() needs it in the passage text before
    # this function ever runs.
    connection.execute("DELETE FROM chunks WHERE source_relative_path = %s", (source.relative_path,))
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
            source.relative_path, source.absolute_path, source.size_bytes, source.modified_utc,
            source.sha256, source.encoding, source.line_count, source.char_count,
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
                chunk.source_relative_path, chunk.source_absolute_path, chunk.source_sha256,
                chunk.line_start, chunk.line_end, chunk.heading, chunk.text, chunk.text_sha256,
                chunk.char_count, embedding, _text_search_input(chunk),
                chunk.business_category, list(chunk.primary_medical_conditions),
                list(chunk.secondary_medical_conditions),
            ),
        )


# Sync data/documents into Postgres: unchanged files (same SHA-256 already
# stored) are skipped entirely; new/changed files are re-chunked, re-embedded,
# and written in one transaction each; files removed from source are deleted.
def build(source: Path, model_name: str, batch_size: int = BATCH_SIZE) -> None:
    source = source.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Source directory does not exist: {source}")

    profile = get_profile(model_name)
    ensure_schema(profile.dimension)
    settings.model_cache_dir.mkdir(parents=True, exist_ok=True)
    pool = get_pool()

    paths = sorted(
        (path for path in source.rglob("*.md") if path.is_file()),
        key=lambda item: item.relative_to(source).as_posix().casefold(),
    )
    if not paths:
        raise RuntimeError(f"No Markdown files found in {source}")

    with pool.connection() as connection:
        with connection.cursor(row_factory=namedtuple_row) as cursor:
            existing = {
                row.relative_path: row.sha256
                for row in cursor.execute("SELECT relative_path, sha256 FROM documents").fetchall()
            }
            stored_version_row = cursor.execute(
                "SELECT value FROM sync_metadata WHERE key = 'text_repr_version'"
            ).fetchone()
            stored_model_row = cursor.execute(
                "SELECT value FROM sync_metadata WHERE key = 'model_name'"
            ).fetchone()

    # A document's own SHA-256 only tells us the *source file* hasn't changed,
    # not that the text representation derived from it (chunking/cleaning
    # rules) is still current. When TEXT_REPR_VERSION has moved on, every
    # document must be treated as new so it gets re-chunked, re-cleaned, and
    # re-embedded under the current rules, even though none of them were
    # touched on disk.
    stored_version = stored_version_row[0] if stored_version_row else None
    # Remembered before a forced resync empties `existing`, so documents removed
    # from the source are still deleted in that same run.
    stored_paths = set(existing)
    if stored_version != TEXT_REPR_VERSION:
        if stored_version is not None:
            print(
                f"Text representation changed ({stored_version} -> {TEXT_REPR_VERSION}); "
                "forcing a full resync",
                flush=True,
            )
        existing = {}

    # Likewise for the model: vectors of two models live in different spaces and
    # must never share an index, so a model change re-embeds every document.
    stored_model = stored_model_row[0] if stored_model_row else None
    if stored_model is not None and stored_model != model_name:
        print(f"Embedding model changed ({stored_model} -> {model_name}); forcing a full resync", flush=True)
        existing = {}

    dictionary = load_dictionary()
    warnings: list[str] = []
    skipped = 0
    pending: list[tuple[SourceFile, list[Fragment]]] = []
    all_new_chunks: list[Chunk] = []
    initial_stats: dict[str, tuple[int, int]] = {}

    def report_progress(index: int) -> None:
        if index % 50 == 0 or index == len(paths):
            print(f"Scanned {index}/{len(paths)} files; {len(pending)} changed, {skipped} unchanged", flush=True)

    for index, path in enumerate(paths, start=1):
        relative = path.relative_to(source).as_posix()
        category_id = path.parent.relative_to(source).as_posix()
        if category_id == ".":
            category_id = ROOT_CATEGORY_ID
        file_hash = sha256_file(path)
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
            modified_utc=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
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
        print(f"Loading local embedding model {model_name} (device {settings.embedding_device})", flush=True)
        model = create_embedding_model(model_name, settings.model_cache_dir)
        print(f"Embedding {len(all_new_chunks)} chunks from {len(pending)} changed files (batch size {batch_size})", flush=True)
        embeddings = embed_chunks(model, all_new_chunks, batch_size, profile)

        changed_during_sync = []
        for relative, (size, mtime_ns) in initial_stats.items():
            current = Path(source, relative).stat()
            if (current.st_size, current.st_mtime_ns) != (size, mtime_ns):
                changed_during_sync.append(relative)
        if changed_during_sync:
            raise RuntimeError("Source files changed during sync: " + ", ".join(changed_during_sync[:10]))

    offset = 0
    for source_file, document_chunks in pending:
        count = len(document_chunks)
        chunk_slice = all_new_chunks[offset:offset + count]
        embedding_slice = embeddings[offset:offset + count]
        offset += count
        with pool.connection() as connection:
            _write_document(connection, source_file, chunk_slice, embedding_slice)

    current_relative_paths = {path.relative_to(source).as_posix() for path in paths}
    removed = sorted(stored_paths - current_relative_paths)
    if removed:
        with pool.connection() as connection:
            connection.execute("DELETE FROM documents WHERE relative_path = ANY(%s)", (removed,))
            connection.commit()

    with pool.connection() as connection:
        connection.execute(
            """
            INSERT INTO sync_metadata (key, value) VALUES (%s, %s), (%s, %s), (%s, %s), (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (
                "model_name", model_name, "model_dimension", str(profile.dimension),
                "last_synced_utc", utc_now(), "text_repr_version", TEXT_REPR_VERSION,
            ),
        )
        connection.commit()

    print(json.dumps({
        "status": "ok",
        "files_scanned": len(paths),
        "files_unchanged": skipped,
        "files_synced": len(pending),
        "files_removed": len(removed),
        "chunks_written": len(all_new_chunks),
        "warnings": len(warnings),
    }, ensure_ascii=False), flush=True)


# Parse command-line options for the incremental index sync.
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    project_root = Path(__file__).resolve().parents[2]
    parser.add_argument("--source", type=Path, default=project_root / "data" / "documents")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    try:
        build(arguments.source, arguments.model)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
