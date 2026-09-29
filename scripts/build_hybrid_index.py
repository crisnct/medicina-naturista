#!/usr/bin/env python3
"""Incrementally sync a traceable, local-only hybrid index for a Markdown
medical corpus into Postgres (pgvector for semantic search, tsvector for
lexical search). A document whose SHA-256 matches what's already stored is
skipped entirely — no re-chunking, no re-embedding, no DB write — so adding
or editing one document never touches the rest of the corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Sequence

import numpy as np
from psycopg.rows import namedtuple_row

from medicina_naturista.ai.categories import ROOT_CATEGORY_ID
from medicina_naturista.ai.db import ensure_schema, get_pool
from medicina_naturista.ai.embedding_model import DEFAULT_MODEL, MODEL_DIMENSION, create_embedding_model
from medicina_naturista.config import settings

# Preferred chunk size; complete content units may extend up to MAX_CHARS.
TARGET_CHARS = 1200
# Hard upper bound for chunk text before embedding.
MAX_CHARS = 1400
# Maximum complete trailing context carried into the next chunk.
OVERLAP_CHARS = 240
# Minimum elapsed time between embedding progress messages.
PROGRESS_INTERVAL_SECONDS = 10.0

# A file with no headings, lists, tables, blockquotes, or code fences and at
# or under this many characters is indexed as a single indivisible fragment
# instead of being split by chunk_document()'s normal block-based logic:
# splitting an unstructured single-topic note (common across this corpus)
# would fragment one remedy description without any real section boundary
# to split on.
UNSTRUCTURED_SINGLE_CHUNK_CHARS = 5000

# Bumped whenever the text representation fed into embeddings/lexical search
# changes (e.g. the cleaning rules below), so build() forces a full resync
# even though every source file's own SHA-256 is unchanged. See build()'s use
# of TEXT_REPR_VERSION against sync_metadata.
TEXT_REPR_VERSION = "2"


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


# Find a readable split point without exceeding the configured chunk limit.
def find_split_boundary(text: str, *, prefer_newline: bool = False) -> int:
    search_end = min(len(text), MAX_CHARS)
    search_start = min(TARGET_CHARS, search_end)
    preferred_start = min(TARGET_CHARS // 2, search_start)
    window = text[:search_end]

    newline = window.rfind("\n", preferred_start, search_end + 1)
    if prefer_newline and newline >= 0:
        return newline + 1

    sentence_ends = [
        match.end()
        for match in re.finditer(r"[.!?…](?:[\"'”’\)\]]*)\s+", window)
        if preferred_start <= match.end() <= search_end
    ]
    if sentence_ends:
        return sentence_ends[-1]
    if newline >= 0:
        return newline + 1

    whitespace = max(
        window.rfind(" ", preferred_start, search_end + 1),
        window.rfind("\t", preferred_start, search_end + 1),
    )
    return whitespace + 1 if whitespace >= 0 else search_end


# Split oversized text at sentence or word boundaries without creating raw overlap.
def split_long_piece(text: str, line_start: int, line_end: int) -> Iterator[tuple[str, int, int]]:
    """Split oversized text, giving each piece its own line range within
    (line_start, line_end) instead of stamping every piece with the whole
    block's range. A block with no blank lines (e.g. one large table row
    after row) is a single multi-thousand-line block to markdown_blocks(), so
    reusing its full range for every split-out piece previously made each
    piece's "context" expand to the entire block when read back from disk."""
    body = text.strip()
    if not body:
        return
    lines = body.splitlines()
    structured = len(lines) > 1 and any(
        re.match(r"^\s*(?:[-*+]\s+|\d+[.)]\s+|\|)", line)
        for line in lines
    )
    total = len(body)
    pos = 0
    while True:
        while pos < total and body[pos].isspace():
            pos += 1
        if total - pos <= MAX_CHARS:
            break
        window = body[pos:]
        cut = find_split_boundary(window, prefer_newline=structured)
        raw_piece = window[:cut]
        piece = raw_piece.strip()
        if piece:
            lead = len(raw_piece) - len(raw_piece.lstrip())
            start_index = pos + lead
            end_index = start_index + len(piece)
            piece_start = line_start + body.count("\n", 0, start_index)
            piece_end = min(line_end, line_start + body.count("\n", 0, end_index))
            yield piece, piece_start, piece_end
        pos += cut
    while pos < total and body[pos].isspace():
        pos += 1
    tail = body[pos:]
    if tail:
        tail_start = line_start + body.count("\n", 0, pos)
        tail_end = min(line_end, line_start + body.count("\n", 0, pos + len(tail)))
        yield tail, tail_start, tail_end


# Treat generated PDF page markers as soft boundaries rather than semantic titles.
def is_page_heading(title: str) -> bool:
    return bool(re.fullmatch(r"(?:pagina|page)\s+\d+(?:\s+(?:din|of)\s+\d+)?", title.strip(), flags=re.IGNORECASE))


# Parse Markdown into heading-aware blocks with source line ranges.
def markdown_blocks(text: str) -> list[tuple[str, int, int, str, str]]:
    lines = text.split("\n")
    blocks: list[tuple[str, int, int, str, str]] = []
    heading_stack: list[tuple[str, bool]] = []
    buffer: list[str] = []
    buffer_start = 1
    pending_boundary = "none"

    # Return semantic headings while excluding generated page-number markers.
    def heading_path() -> str:
        return " > ".join(title for title, is_soft in heading_stack if not is_soft)

    # Emit the buffered non-empty block and reset the line buffer.
    def flush(end_line: int) -> None:
        nonlocal buffer, pending_boundary
        body = "\n".join(buffer).strip()
        if body:
            blocks.append((body, buffer_start, end_line, heading_path(), pending_boundary))
            pending_boundary = "none"
        buffer = []

    for number, line in enumerate(lines, start=1):
        match = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if match:
            flush(number - 1)
            level = len(match.group(1))
            title = match.group(2).strip()
            soft_boundary = is_page_heading(title)
            heading_stack[:] = heading_stack[: level - 1]
            heading_stack.append((title, soft_boundary))
            if not soft_boundary:
                pending_boundary = "hard"
            elif pending_boundary == "none":
                pending_boundary = "soft"
            continue
        if not line.strip():
            flush(number - 1)
            continue
        if not buffer:
            buffer_start = number
        buffer.append(line.rstrip())
    flush(len(lines))
    return blocks


# Matches a line that starts a heading, list item, table row, blockquote, or
# code fence — the same markers chunk_document() otherwise splits around.
_STRUCTURE_LINE_RE = re.compile(r"^\s{0,3}(?:#{1,6}\s|[-*+]\s|\d+[.)]\s|\||>|```)")


# True if any line in text opens a heading/list/table/blockquote/code block.
def _has_markdown_structure(text: str) -> bool:
    return any(_STRUCTURE_LINE_RE.match(line) for line in text.split("\n"))


# Combine Markdown blocks into bounded overlapping chunks for embedding.
def chunk_document(text: str) -> list[tuple[str, int, int, str]]:
    stripped = text.strip()
    if (
        stripped
        and len(stripped) <= UNSTRUCTURED_SINGLE_CHUNK_CHARS
        and not _has_markdown_structure(text)
    ):
        return [(stripped, 1, text.count("\n") + 1, "")]

    raw_blocks = markdown_blocks(text)
    pieces: list[tuple[str, int, int, str, str]] = []
    for body, start, end, heading, boundary in raw_blocks:
        for index, (piece, piece_start, piece_end) in enumerate(split_long_piece(body, start, end)):
            pieces.append((piece, piece_start, piece_end, heading, boundary if index == 0 else "none"))

    chunks: list[tuple[str, int, int, str]] = []
    current: list[tuple[str, int, int, str, str]] = []
    current_chars = 0
    new_content_items = 0

    # Return trailing complete units that fit entirely inside the overlap budget.
    def trailing_overlap() -> list[tuple[str, int, int, str, str]]:
        overlap: list[tuple[str, int, int, str, str]] = []
        size = 0
        for item in reversed(current):
            item_size = len(item[0]) + (2 if overlap else 0)
            if size + item_size > OVERLAP_CHARS:
                break
            overlap.insert(0, item)
            size += item_size
        return overlap

    # Carry one complete sentence or short unit over a generated page boundary.
    def page_sentence_overlap() -> list[tuple[str, int, int, str, str]]:
        if not current:
            return []
        item = current[-1]
        matches = list(re.finditer(r"[^.!?…]+[.!?…](?:[\"'”’\)\]]*)", item[0], flags=re.DOTALL))
        candidate = matches[-1].group(0).strip() if matches else item[0].strip()
        if not candidate or len(candidate) > OVERLAP_CHARS:
            return []
        return [(candidate, item[1], item[2], item[3], "none")]

    # Emit only chunks containing new content; optionally retain bounded overlap.
    def flush(retain_overlap: bool) -> None:
        nonlocal current, current_chars, new_content_items
        if not current or new_content_items == 0:
            return
        combined = "\n\n".join(item[0] for item in current).strip()
        start = min(item[1] for item in current)
        end = max(item[2] for item in current)
        heading = current[-1][3]
        if combined:
            if len(combined) > MAX_CHARS:
                raise RuntimeError(f"Chunk exceeds {MAX_CHARS} characters: {len(combined)}")
            chunks.append((combined, start, end, heading))
        current = trailing_overlap() if retain_overlap else []
        current_chars = sum(len(item[0]) for item in current) + max(0, len(current) - 1) * 2
        new_content_items = 0

    for piece in pieces:
        boundary = piece[4]
        if boundary == "hard":
            flush(retain_overlap=False)
            current = []
            current_chars = 0
            new_content_items = 0
        elif boundary == "soft":
            overlap = page_sentence_overlap()
            flush(retain_overlap=False)
            current = overlap
            current_chars = sum(len(item[0]) for item in current) + max(0, len(current) - 1) * 2
            new_content_items = 0

        additional = len(piece[0]) + (2 if current else 0)
        if current and current_chars + additional > MAX_CHARS:
            flush(retain_overlap=True)
            additional = len(piece[0]) + (2 if current else 0)
            if current and current_chars + additional > MAX_CHARS:
                current = []
                current_chars = 0
                additional = len(piece[0])
        current.append(piece)
        current_chars += additional
        new_content_items += 1
        if current_chars >= TARGET_CHARS:
            flush(retain_overlap=True)
    flush(retain_overlap=False)
    return chunks


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


# Convert chunks into model inputs containing source context and passage text.
def iter_embedding_inputs(chunks: Sequence[Chunk]) -> Iterator[str]:
    for chunk in chunks:
        yield f"passage: {_embedding_context(chunk)}\n{chunk.text}"


# Embed a single oversized chunk (only ever the whole-file fragment from the
# unstructured-file bypass in chunk_document(), up to
# UNSTRUCTURED_SINGLE_CHUNK_CHARS) on overlapping MAX_CHARS windows, then
# average and re-normalize into one vector of the same shape every other
# chunk gets — the ONNX model would otherwise silently truncate the input
# instead of raising, silently dropping the tail of the fragment.
def _embed_long_chunk(model: object, chunk: Chunk) -> np.ndarray:
    context = _embedding_context(chunk)
    text = chunk.text
    step = MAX_CHARS - OVERLAP_CHARS
    windows = []
    position = 0
    while True:
        window = text[position:position + MAX_CHARS]
        windows.append(f"passage: {context}\n{window}")
        if position + MAX_CHARS >= len(text):
            break
        position += step
    vectors = np.asarray(
        list(model.embed(windows, batch_size=len(windows), parallel=None)), dtype=np.float32
    )
    averaged = vectors.mean(axis=0)
    norm = np.linalg.norm(averaged)
    if not np.isfinite(norm) or norm == 0:
        raise RuntimeError(
            f"Windowed embedding produced a non-finite or zero vector for {chunk.source_relative_path}"
        )
    return averaged / norm


# Format elapsed and estimated durations as stable terminal-friendly timestamps.
def format_duration(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


# Generate, validate, and normalize embeddings while reporting measured progress.
def embed_chunks(
    model: object,
    chunks: Sequence[Chunk],
    batch_size: int,
    *,
    progress_interval_seconds: float = PROGRESS_INTERVAL_SECONDS,
    clock: Callable[[], float] | None = None,
) -> np.ndarray:
    if progress_interval_seconds <= 0:
        raise ValueError("Progress interval must be greater than zero")

    monotonic = clock or time.monotonic
    total = len(chunks)
    # Chunks over MAX_CHARS only ever come from the unstructured-file bypass
    # in chunk_document(); they're embedded separately via _embed_long_chunk()
    # (see below) instead of through the batched model.embed() call, which
    # would silently truncate them. When there are none (the common case),
    # normal_chunks == chunks and this loop's behaviour is unchanged.
    normal_indices = [index for index, chunk in enumerate(chunks) if len(chunk.text) <= MAX_CHARS]
    long_indices = [index for index, chunk in enumerate(chunks) if len(chunk.text) > MAX_CHARS]
    normal_chunks = [chunks[index] for index in normal_indices]
    normal_total = len(normal_chunks)

    vectors: list[np.ndarray] = []
    started = monotonic()
    last_report = started

    for processed, vector in enumerate(
        model.embed(iter_embedding_inputs(normal_chunks), batch_size=batch_size, parallel=None),
        start=1,
    ):
        vectors.append(vector)
        now = monotonic()
        if processed < normal_total and now - last_report >= progress_interval_seconds:
            elapsed = max(now - started, 1e-9)
            rate = processed / elapsed
            eta = (normal_total - processed) / rate if rate > 0 else 0.0
            percent = processed * 100.0 / normal_total
            print(
                f"Embedding progress: {processed}/{normal_total} ({percent:.1f}%) | "
                f"elapsed {format_duration(elapsed)} | rate {rate:.1f} chunks/s | "
                f"ETA {format_duration(eta)}",
                flush=True,
            )
            last_report = now

    normal_embeddings = np.asarray(vectors, dtype=np.float32)
    if normal_total and normal_embeddings.shape != (normal_total, MODEL_DIMENSION):
        raise RuntimeError(f"Unexpected embedding matrix shape: {normal_embeddings.shape}")
    if normal_total:
        norms = np.linalg.norm(normal_embeddings, axis=1)
        if not np.isfinite(normal_embeddings).all() or np.any(norms == 0):
            raise RuntimeError("Embedding matrix contains non-finite or zero vectors")
        normal_embeddings /= norms[:, None]

    embeddings = np.zeros((total, MODEL_DIMENSION), dtype=np.float32)
    for position, chunk_index in enumerate(normal_indices):
        embeddings[chunk_index] = normal_embeddings[position]
    for chunk_index in long_indices:
        embeddings[chunk_index] = _embed_long_chunk(model, chunks[chunk_index])

    elapsed = monotonic() - started
    rate = total / max(elapsed, 1e-9)
    print(
        f"Embedding completed: {total}/{total} (100.0%) | "
        f"elapsed {format_duration(elapsed)} | rate {rate:.1f} chunks/s",
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
                 heading, text, text_sha256, char_count, embedding, text_search)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, to_tsvector('simple', unaccent(%s)))
            """,
            (
                chunk.source_relative_path, chunk.source_absolute_path, chunk.source_sha256,
                chunk.line_start, chunk.line_end, chunk.heading, chunk.text, chunk.text_sha256,
                chunk.char_count, embedding, _text_search_input(chunk),
            ),
        )


# Sync data/documents into Postgres: unchanged files (same SHA-256 already
# stored) are skipped entirely; new/changed files are re-chunked, re-embedded,
# and written in one transaction each; files removed from source are deleted.
def build(source: Path, model_name: str, batch_size: int) -> None:
    source = source.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Source directory does not exist: {source}")

    ensure_schema()
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

    # A document's own SHA-256 only tells us the *source file* hasn't changed,
    # not that the text representation derived from it (chunking/cleaning
    # rules) is still current. When TEXT_REPR_VERSION has moved on, every
    # document must be treated as new so it gets re-chunked, re-cleaned, and
    # re-embedded under the current rules, even though none of them were
    # touched on disk.
    stored_version = stored_version_row[0] if stored_version_row else None
    if stored_version != TEXT_REPR_VERSION:
        if stored_version is not None:
            print(
                f"Text representation changed ({stored_version} -> {TEXT_REPR_VERSION}); "
                "forcing a full resync",
                flush=True,
            )
        existing = {}

    warnings: list[str] = []
    skipped = 0
    pending: list[tuple[SourceFile, list[tuple[str, int, int, str]]]] = []
    all_new_chunks: list[Chunk] = []
    initial_stats: dict[str, tuple[int, int]] = {}

    for index, path in enumerate(paths, start=1):
        relative = path.relative_to(source).as_posix()
        category_id = path.parent.relative_to(source).as_posix()
        if category_id == ".":
            category_id = ROOT_CATEGORY_ID
        file_hash = sha256_file(path)
        if existing.get(relative) == file_hash:
            skipped += 1
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
        document_chunks = chunk_document(normalized)
        if not document_chunks:
            warnings.append(f"No indexable text: {relative}")
        pending.append((source_file, document_chunks))
        for body, line_start, line_end, heading in document_chunks:
            all_new_chunks.append(
                Chunk(
                    source_relative_path=relative,
                    source_absolute_path=str(path),
                    source_sha256=source_hash,
                    line_start=line_start,
                    line_end=line_end,
                    heading=heading,
                    text=body,
                    text_sha256=sha256_bytes(body.encode("utf-8")),
                    char_count=len(body),
                    category_id=category_id,
                )
            )
        if index % 50 == 0 or index == len(paths):
            print(f"Scanned {index}/{len(paths)} files; {len(pending)} changed, {skipped} unchanged", flush=True)

    embeddings = np.empty((0, MODEL_DIMENSION), dtype=np.float32)
    if all_new_chunks:
        print(f"Loading local embedding model {model_name}", flush=True)
        model = create_embedding_model(model_name, MODEL_DIMENSION, settings.model_cache_dir)
        print(f"Embedding {len(all_new_chunks)} chunks from {len(pending)} changed files (batch size {batch_size})", flush=True)
        embeddings = embed_chunks(model, all_new_chunks, batch_size)

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
    removed = sorted(set(existing) - current_relative_paths)
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
                "model_name", model_name, "model_dimension", str(MODEL_DIMENSION),
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
    project_root = Path(__file__).resolve().parents[1]
    parser.add_argument("--source", type=Path, default=project_root / "data" / "documents")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--batch-size", type=int, default=64)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    try:
        build(arguments.source, arguments.model, arguments.batch_size)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
