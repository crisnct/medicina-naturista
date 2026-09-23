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
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Sequence

import numpy as np


DEFAULT_MODEL = "intfloat/multilingual-e5-small"
MODEL_DIMENSION = 384
MODEL_FILE = "onnx/model.onnx"
TARGET_CHARS = 1200
MAX_CHARS = 1600
OVERLAP_CHARS = 180


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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def read_markdown(path: Path) -> tuple[str, str, bytes]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1250", "cp1252"):
        try:
            return raw.decode(encoding), encoding, raw
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8-replace", raw


def normalize_text(text: str) -> str:
    return text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")


def split_long_piece(text: str, line_start: int, line_end: int) -> Iterator[tuple[str, int, int]]:
    """Split oversized text near whitespace while retaining conservative line bounds."""
    remaining = text.strip()
    while len(remaining) > MAX_CHARS:
        cut = remaining.rfind(" ", TARGET_CHARS, MAX_CHARS + 1)
        if cut < TARGET_CHARS // 2:
            cut = remaining.find(" ", TARGET_CHARS)
        if cut < 0 or cut > MAX_CHARS:
            cut = MAX_CHARS
        piece = remaining[:cut].strip()
        if piece:
            yield piece, line_start, line_end
        tail_start = max(0, cut - OVERLAP_CHARS)
        remaining = remaining[tail_start:].strip()
    if remaining:
        yield remaining, line_start, line_end


def markdown_blocks(text: str) -> list[tuple[str, int, int, str]]:
    lines = text.split("\n")
    blocks: list[tuple[str, int, int, str]] = []
    heading_stack: list[str] = []
    buffer: list[str] = []
    buffer_start = 1

    def heading_path() -> str:
        return " > ".join(heading_stack)

    def flush(end_line: int) -> None:
        nonlocal buffer
        body = "\n".join(buffer).strip()
        if body:
            blocks.append((body, buffer_start, end_line, heading_path()))
        buffer = []

    for number, line in enumerate(lines, start=1):
        match = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if match:
            flush(number - 1)
            level = len(match.group(1))
            title = match.group(2).strip()
            heading_stack[:] = heading_stack[: level - 1]
            heading_stack.append(title)
            blocks.append((line.strip(), number, number, heading_path()))
            continue
        if not line.strip():
            flush(number - 1)
            continue
        if not buffer:
            buffer_start = number
        buffer.append(line.rstrip())
    flush(len(lines))
    return blocks


def chunk_document(text: str) -> list[tuple[str, int, int, str]]:
    raw_blocks = markdown_blocks(text)
    pieces: list[tuple[str, int, int, str]] = []
    for body, start, end, heading in raw_blocks:
        for piece, piece_start, piece_end in split_long_piece(body, start, end):
            pieces.append((piece, piece_start, piece_end, heading))

    chunks: list[tuple[str, int, int, str]] = []
    current: list[tuple[str, int, int, str]] = []
    current_chars = 0

    def flush() -> None:
        nonlocal current, current_chars
        if not current:
            return
        combined = "\n\n".join(item[0] for item in current).strip()
        start = min(item[1] for item in current)
        end = max(item[2] for item in current)
        heading = next((item[3] for item in reversed(current) if item[3]), "")
        if combined:
            chunks.append((combined, start, end, heading))
        if len(combined) > OVERLAP_CHARS and len(current) > 1:
            overlap: list[tuple[str, int, int, str]] = []
            size = 0
            for item in reversed(current):
                overlap.insert(0, item)
                size += len(item[0]) + 2
                if size >= OVERLAP_CHARS:
                    break
            current = overlap
            current_chars = sum(len(item[0]) + 2 for item in current)
        else:
            current = []
            current_chars = 0

    for piece in pieces:
        additional = len(piece[0]) + (2 if current else 0)
        if current and current_chars + additional > MAX_CHARS:
            flush()
        current.append(piece)
        current_chars += additional
        if current_chars >= TARGET_CHARS:
            flush()
    flush()
    return chunks


def iter_embedding_inputs(chunks: Sequence[Chunk]) -> Iterator[str]:
    for chunk in chunks:
        context = Path(chunk.source_relative_path).stem
        if chunk.heading:
            context += f"\n{chunk.heading}"
        yield f"passage: {context}\n{chunk.text}"


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


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[object]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            if hasattr(row, "__dataclass_fields__"):
                row = asdict(row)
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


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


def build(source: Path, output: Path, model_name: str, batch_size: int) -> None:
    source = source.resolve()
    output = output.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Source directory does not exist: {source}")
    if source == output or source in output.parents:
        raise ValueError("Output directory must not be inside the source directory")

    output.mkdir(parents=True, exist_ok=True)
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
    print(f"Embedding {len(chunks)} chunks", flush=True)
    embeddings = np.asarray(
        list(model.embed(iter_embedding_inputs(chunks), batch_size=batch_size, parallel=None)),
        dtype=np.float32,
    )
    if embeddings.shape != (len(chunks), MODEL_DIMENSION):
        raise RuntimeError(f"Unexpected embedding matrix shape: {embeddings.shape}")
    norms = np.linalg.norm(embeddings, axis=1)
    if not np.isfinite(embeddings).all() or np.any(norms == 0):
        raise RuntimeError("Embedding matrix contains non-finite or zero vectors")
    embeddings /= norms[:, None]

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

    staging = Path(tempfile.mkdtemp(prefix="index-build-", dir=output))
    try:
        np.save(staging / "embeddings.npy", embeddings, allow_pickle=False)
        write_jsonl(staging / "chunks.jsonl", chunks)
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
            "output_root": str(output),
            "source_file_count": len(source_files),
            "source_total_bytes": sum(item.size_bytes for item in source_files),
            "source_digest_sha256": source_digest,
            "chunk_count": len(chunks),
            "chunking": {
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
            "index": {"semantic": "embeddings.npy", "lexical": "index.sqlite3 FTS5"},
            "warnings": warnings,
            "medical_use_notice": (
                "Retrieval index only. Source claims may be inaccurate, contradictory, or unsafe. "
                "Future medical outputs must cite source paths, distinguish evidence from claims, "
                "and must not replace diagnosis or professional care."
            ),
        }
        write_json(staging / "manifest.json", manifest)

        core_names = ["chunks.jsonl", "embeddings.npy", "index.sqlite3", "manifest.json", "source_manifest.jsonl"]
        checksum_lines = [f"{sha256_file(staging / name)}  {name}" for name in core_names]
        (staging / "SHA256SUMS.txt").write_text("\n".join(checksum_lines) + "\n", encoding="ascii")

        for name in core_names + ["SHA256SUMS.txt"]:
            os.replace(staging / name, output / name)
    finally:
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
        "output": str(output),
    }, ensure_ascii=False), flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parent / "documents")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--batch-size", type=int, default=64)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    try:
        build(arguments.source, arguments.output, arguments.model, arguments.batch_size)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
