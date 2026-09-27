#!/usr/bin/env python3
"""Build a traceable, local-only hybrid index for a Markdown medical corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Iterator, Sequence

import numpy as np

# Default multilingual model used for Romanian and English medical retrieval.
DEFAULT_MODEL = "intfloat/multilingual-e5-small"
# Vector width produced by DEFAULT_MODEL and required by the generated index.
MODEL_DIMENSION = 384
# ONNX artifact loaded from the local Hugging Face model snapshot.
MODEL_FILE = "onnx/model.onnx"
# Preferred chunk size; complete content units may extend up to MAX_CHARS.
TARGET_CHARS = 1200
# Hard upper bound for chunk text before embedding.
MAX_CHARS = 1400
# Maximum complete trailing context carried into the next chunk.
OVERLAP_CHARS = 240
# Minimum elapsed time between embedding progress messages.
PROGRESS_INTERVAL_SECONDS = 10.0
# Directory containing the complete semantic and lexical retrieval index.
INDEX_DIRECTORY_NAME = "hybrid_index"
# Traceable JSON Lines export of the fragments represented by the index.
FRAGMENTS_FILE_NAME = "fragments.jsonl"
INDEX_FILE_NAMES = (FRAGMENTS_FILE_NAME, "embeddings.npy", "index.sqlite3", "manifest.json", "source_manifest.jsonl", "SHA256SUMS.txt")

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


@dataclass(frozen=True)
class Chunk:
    chunk_id: int
    embedding_row: int
    source_relative_path: str
    source_absolute_path: str
    source_sha256: str
    line_start: int
    line_end: int
    heading: str
    text: str
    text_sha256: str
    char_count: int


# Return the current UTC timestamp in a stable ISO-8601 representation.
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# Compute the SHA-256 digest of an in-memory byte sequence.
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# Compute a file digest incrementally to keep memory usage bounded.
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


# Combine Markdown blocks into bounded overlapping chunks for embedding.
def chunk_document(text: str) -> list[tuple[str, int, int, str]]:
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


# Convert chunks into model inputs containing source context and passage text.
def iter_embedding_inputs(chunks: Sequence[Chunk]) -> Iterator[str]:
    for chunk in chunks:
        context = Path(chunk.source_relative_path).stem
        if chunk.heading:
            context += f"\n{chunk.heading}"
        yield f"passage: {context}\n{chunk.text}"


# Load or register the configured FastEmbed model in the local cache.
def create_embedding_model(model_name: str, cache_dir: Path):
    from fastembed import TextEmbedding

    supported = {item["model"] for item in TextEmbedding.list_supported_models()}
    if model_name not in supported:
        from fastembed.common.model_description import ModelSource, PoolingType

        TextEmbedding.add_custom_model(
            model=model_name,
            pooling=PoolingType.MEAN,
            normalization=True,
            sources=ModelSource(hf=model_name),
            dim=MODEL_DIMENSION,
            model_file=MODEL_FILE,
        )
    return TextEmbedding(model_name=model_name, cache_dir=str(cache_dir), threads=max(1, (os.cpu_count() or 2) - 1))


# Serialize one JSON value as readable UTF-8 text.
def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# Serialize an iterable of values or dataclass records as compact JSON Lines.
def write_jsonl(path: Path, rows: Iterable[object]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            if hasattr(row, "__dataclass_fields__"):
                row = asdict(row)
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


# Create the SQLite metadata, chunk, and FTS5 tables for the generated index.
def create_sqlite(path: Path, sources: Sequence[SourceFile], chunks: Sequence[Chunk], metadata: dict[str, str]) -> None:
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            PRAGMA journal_mode=DELETE;
            PRAGMA synchronous=FULL;
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE files (
                relative_path TEXT PRIMARY KEY,
                absolute_path TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                modified_utc TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                encoding TEXT NOT NULL,
                line_count INTEGER NOT NULL,
                char_count INTEGER NOT NULL
            );
            CREATE TABLE chunks (
                chunk_id INTEGER PRIMARY KEY,
                embedding_row INTEGER UNIQUE NOT NULL,
                source_relative_path TEXT NOT NULL REFERENCES files(relative_path),
                source_absolute_path TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                line_start INTEGER NOT NULL,
                line_end INTEGER NOT NULL,
                heading TEXT NOT NULL,
                text TEXT NOT NULL,
                text_sha256 TEXT NOT NULL,
                char_count INTEGER NOT NULL
            );
            CREATE INDEX idx_chunks_source ON chunks(source_relative_path, line_start);
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
                text, heading, source_relative_path,
                tokenize='unicode61 remove_diacritics 2'
            );
            """
        )
        connection.executemany("INSERT INTO metadata(key,value) VALUES (?,?)", sorted(metadata.items()))
        connection.executemany(
            "INSERT INTO files VALUES (?,?,?,?,?,?,?,?)",
            [tuple(asdict(item).values()) for item in sources],
        )
        chunk_rows = [tuple(asdict(item).values()) for item in chunks]
        connection.executemany("INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?)", chunk_rows)
        connection.executemany(
            "INSERT INTO chunks_fts(rowid,text,heading,source_relative_path) VALUES (?,?,?,?)",
            [(item.chunk_id, item.text, item.heading, item.source_relative_path) for item in chunks],
        )
        connection.commit()
        result = connection.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError(f"SQLite integrity_check failed: {result}")
    finally:
        connection.close()


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
    vectors: list[np.ndarray] = []
    started = monotonic()
    last_report = started

    for processed, vector in enumerate(
        model.embed(iter_embedding_inputs(chunks), batch_size=batch_size, parallel=None),
        start=1,
    ):
        vectors.append(vector)
        now = monotonic()
        if processed < total and now - last_report >= progress_interval_seconds:
            elapsed = max(now - started, 1e-9)
            rate = processed / elapsed
            eta = (total - processed) / rate if rate > 0 else 0.0
            percent = processed * 100.0 / total
            print(
                f"Embedding progress: {processed}/{total} ({percent:.1f}%) | "
                f"elapsed {format_duration(elapsed)} | rate {rate:.1f} chunks/s | "
                f"ETA {format_duration(eta)}",
                flush=True,
            )
            last_report = now

    embeddings = np.asarray(vectors, dtype=np.float32)
    if embeddings.shape != (total, MODEL_DIMENSION):
        raise RuntimeError(f"Unexpected embedding matrix shape: {embeddings.shape}")
    norms = np.linalg.norm(embeddings, axis=1)
    if not np.isfinite(embeddings).all() or np.any(norms == 0):
        raise RuntimeError("Embedding matrix contains non-finite or zero vectors")
    embeddings /= norms[:, None]

    elapsed = monotonic() - started
    rate = total / max(elapsed, 1e-9)
    print(
        f"Embedding completed: {total}/{total} (100.0%) | "
        f"elapsed {format_duration(elapsed)} | rate {rate:.1f} chunks/s",
        flush=True,
    )
    return embeddings


# Fail fast if another program (editor, IDE, ...) holds existing index files, since Windows then refuses to replace them.
def ensure_index_files_replaceable(index_dir: Path) -> None:
    locked: list[str] = []
    for name in INDEX_FILE_NAMES:
        path = index_dir / name
        if not path.exists():
            continue
        probe = path.with_name(path.name + ".lockcheck")
        try:
            os.replace(path, probe)
            os.replace(probe, path)
        except OSError:
            locked.append(name)
    if locked:
        raise PermissionError(
            f"Index files are in use by another program: {', '.join(locked)}. "
            "Close them in your editor/IDE (and stop anything reading them), then run the build again."
        )


# Build embeddings, searchable metadata, checksums, and manifests atomically.
def build(
    source: Path,
    output: Path,
    model_name: str,
    batch_size: int,
    before_publish: Callable[[], None] | None = None,
) -> None:
    source = source.resolve()
    output = output.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Source directory does not exist: {source}")
    if source == output or source in output.parents:
        raise ValueError("Output directory must not be inside the source directory")

    output.mkdir(parents=True, exist_ok=True)
    index_dir = output / INDEX_DIRECTORY_NAME
    index_dir.mkdir(parents=True, exist_ok=True)
    ensure_index_files_replaceable(index_dir)
    cache_dir = output / "model_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    started_at = utc_now()

    paths = sorted(
        (path for path in source.rglob("*.md") if path.is_file()),
        key=lambda item: item.relative_to(source).as_posix().casefold(),
    )
    if not paths:
        raise RuntimeError(f"No Markdown files found in {source}")

    source_files: list[SourceFile] = []
    chunks: list[Chunk] = []
    warnings: list[str] = []
    initial_stats: dict[str, tuple[int, int]] = {}
    next_id = 1

    for index, path in enumerate(paths, start=1):
        relative = path.relative_to(source).as_posix()
        stat = path.stat()
        initial_stats[relative] = (stat.st_size, stat.st_mtime_ns)
        decoded, encoding, raw = read_markdown(path)
        normalized = normalize_text(decoded)
        if encoding == "utf-8-replace":
            warnings.append(f"Replacement characters used while decoding: {relative}")
        line_count = normalized.count("\n") + 1
        source_hash = sha256_bytes(raw)
        source_files.append(
            SourceFile(
                relative_path=relative,
                absolute_path=str(path),
                size_bytes=len(raw),
                modified_utc=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
                sha256=source_hash,
                encoding=encoding,
                line_count=line_count,
                char_count=len(normalized),
            )
        )
        document_chunks = chunk_document(normalized)
        if not document_chunks:
            warnings.append(f"No indexable text: {relative}")
        for body, line_start, line_end, heading in document_chunks:
            chunks.append(
                Chunk(
                    chunk_id=next_id,
                    embedding_row=next_id - 1,
                    source_relative_path=relative,
                    source_absolute_path=str(path),
                    source_sha256=source_hash,
                    line_start=line_start,
                    line_end=line_end,
                    heading=heading,
                    text=body,
                    text_sha256=sha256_bytes(body.encode("utf-8")),
                    char_count=len(body),
                )
            )
            next_id += 1
        if index % 50 == 0 or index == len(paths):
            print(f"Prepared {index}/{len(paths)} files; {len(chunks)} chunks", flush=True)

    if not chunks:
        raise RuntimeError("No chunks were produced")

    print(f"Loading local embedding model {model_name}", flush=True)
    model = create_embedding_model(model_name, cache_dir)
    print(f"Embedding {len(chunks)} chunks (batch size {batch_size})", flush=True)
    embeddings = embed_chunks(model, chunks, batch_size)

    changed_during_build: list[str] = []
    for path in paths:
        relative = path.relative_to(source).as_posix()
        stat = path.stat()
        if initial_stats[relative] != (stat.st_size, stat.st_mtime_ns):
            changed_during_build.append(relative)
    if changed_during_build:
        raise RuntimeError("Source files changed during build: " + ", ".join(changed_during_build[:10]))

    metadata = {
        "schema_version": "1",
        "source_root": str(source),
        "created_utc": started_at,
        "model_name": model_name,
        "model_dimension": str(MODEL_DIMENSION),
        "chunk_count": str(len(chunks)),
        "source_file_count": str(len(source_files)),
    }

    staging = Path(tempfile.mkdtemp(prefix="index-build-", dir=index_dir))
    published = False
    try:
        np.save(staging / "embeddings.npy", embeddings, allow_pickle=False)
        write_jsonl(staging / FRAGMENTS_FILE_NAME, chunks)
        write_jsonl(staging / "source_manifest.jsonl", source_files)
        create_sqlite(staging / "index.sqlite3", source_files, chunks, metadata)

        source_digest = sha256_bytes(
            "\n".join(f"{item.relative_path}\t{item.sha256}" for item in source_files).encode("utf-8")
        )
        manifest = {
            "schema_version": 1,
            "created_utc": started_at,
            "completed_utc": utc_now(),
            "source_root": str(source),
            "output_root": str(index_dir),
            "source_file_count": len(source_files),
            "source_total_bytes": sum(item.size_bytes for item in source_files),
            "source_digest_sha256": source_digest,
            "chunk_count": len(chunks),
            "chunking": {
                "strategy_version": 2,
                "strategy": "Markdown headings and paragraphs with bounded character windows",
                "target_chars": TARGET_CHARS,
                "max_chars": MAX_CHARS,
                "overlap_chars": OVERLAP_CHARS,
            },
            "embedding": {
                "model": model_name,
                "dimension": MODEL_DIMENSION,
                "dtype": "float32",
                "normalized": True,
                "document_prefix": "passage: ",
                "query_prefix": "query: ",
                "inference": "local ONNX via FastEmbed",
            },
            "index": {
                "semantic": "embeddings.npy",
                "lexical": "index.sqlite3 FTS5",
                "fragments": FRAGMENTS_FILE_NAME,
            },
            "warnings": warnings,
            "medical_use_notice": (
                "Retrieval index only. Source claims may be inaccurate, contradictory, or unsafe. "
                "Future medical outputs must cite source paths, distinguish evidence from claims, "
                "and must not replace diagnosis or professional care."
            ),
        }
        write_json(staging / "manifest.json", manifest)

        core_names = [
            FRAGMENTS_FILE_NAME,
            "embeddings.npy",
            "index.sqlite3",
            "manifest.json",
            "source_manifest.jsonl",
        ]
        checksum_lines = [f"{sha256_file(staging / name)}  {name}" for name in core_names]
        (staging / "SHA256SUMS.txt").write_text("\n".join(checksum_lines) + "\n", encoding="ascii")

        if before_publish is not None:
            before_publish()
        try:
            for name in core_names + ["SHA256SUMS.txt"]:
                os.replace(staging / name, index_dir / name)
        except OSError as exc:
            raise RuntimeError(
                f"Could not publish the new index ({exc}). It is complete in {staging}; "
                "close whatever holds the files and move them into the index directory manually."
            ) from exc
        published = True
    finally:
        if published:
            try:
                staging.rmdir()
            except OSError:
                pass

    print(json.dumps({
        "status": "ok",
        "source_files": len(source_files),
        "chunks": len(chunks),
        "embedding_shape": list(embeddings.shape),
        "warnings": len(warnings),
        "output": str(index_dir),
    }, ensure_ascii=False), flush=True)


# Parse command-line options for the embedding index build.
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    project_root = Path(__file__).resolve().parents[1]
    parser.add_argument("--source", type=Path, default=project_root / "data" / "documents")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--skip-docker", action="store_true", help="Do not stop/start the docker compose stack")
    return parser.parse_args()


# Run a docker compose command from the project root; fail loudly if it does not succeed.
def docker_compose(*compose_args: str) -> None:
    project_root = Path(__file__).resolve().parents[1]
    command = ["docker", "compose", *compose_args]
    print(f"Running: {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=project_root, check=True)


if __name__ == "__main__":
    arguments = parse_args()
    try:
        # The app stays online during the long embedding step and is stopped only while the new files are swapped in.
        build(
            arguments.source,
            arguments.output,
            arguments.model,
            arguments.batch_size,
            before_publish=None if arguments.skip_docker else lambda: docker_compose("down"),
        )
        if not arguments.skip_docker:
            docker_compose("up", "-d", "--build")
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
