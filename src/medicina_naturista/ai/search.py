#!/usr/bin/env python3
"""Offline hybrid search over the generated local medical index."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sqlite3
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

# Reciprocal Rank Fusion constant used to combine semantic and lexical ranks
# into hybrid_score (see rank() below). A fragment ranked #1 by both signals
# scores 1/(RRF_K + 1) per signal, so RRF_MAX_SCORE is the highest hybrid_score
# any fragment can ever reach — the fixed ceiling other layers (the UI's
# score-to-percentage display) can rely on without duplicating this constant.
RRF_K = 60.0
RRF_MAX_SCORE = 2.0 / (RRF_K + 1.0)


# Normalize cached FastEmbed metadata paths so Windows caches work in Linux containers.
def _normalize_fastembed_metadata(cache_dir: Path) -> None:
    """Make FastEmbed metadata created on Windows portable to Linux containers."""
    for metadata_file in cache_dir.glob("models--*/files_metadata.json"):
        try:
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            normalized = {str(path).replace("\\", "/"): value for path, value in metadata.items()}
            if normalized != metadata:
                metadata_file.write_text(
                    json.dumps(normalized, ensure_ascii=False),
                    encoding="utf-8",
                )
        except (OSError, ValueError, TypeError):
            continue


@lru_cache(maxsize=4)
# Load or register the offline FastEmbed model used for semantic search.
def create_model(model_name: str, dimension: int, cache_dir: Path):
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")
    _normalize_fastembed_metadata(cache_dir)
    from fastembed import TextEmbedding

    supported = {item["model"] for item in TextEmbedding.list_supported_models()}
    if model_name not in supported:
        from fastembed.common.model_description import ModelSource, PoolingType

        TextEmbedding.add_custom_model(
            model=model_name,
            pooling=PoolingType.MEAN,
            normalization=True,
            sources=ModelSource(hf=model_name),
            dim=dimension,
            model_file="onnx/model.onnx",
        )
    return TextEmbedding(model_name=model_name, cache_dir=str(cache_dir), threads=max(1, (os.cpu_count() or 2) - 1))


# Build a single FTS5 phrase clause from a text segment (words in exact, adjacent order).
def _fts_phrase(segment: str) -> str | None:
    words = re.findall(r"[^\W_]+", segment, flags=re.UNICODE)[:32]
    if not words:
        return None
    joined = " ".join(words)
    return f'"{joined.replace(chr(34), chr(34) * 2)}"'


# Convert user text into a bounded SQLite FTS5 query: comma-separated segments become
# separate exact-phrase clauses combined with OR; a segment with 2+ words is searched
# as a strict phrase (words adjacent, in that order).
def fts_query(text: str) -> str:
    if "," in text:
        clauses = [_fts_phrase(segment) for segment in text.split(",")]
        return " OR ".join(clause for clause in clauses if clause)
    return _fts_phrase(text) or ""


# Combine semantic and lexical rankings with reciprocal rank fusion. Both
# signals always run — there is no per-call or per-deployment toggle to turn
# either off — so every fragment's hybrid_score is a genuine fusion of the
# two ranks, never a single-signal score dressed up in RRF's positional
# formula. Each result also carries one independent boolean per signal
# ("found_by_lexical", "found_by_semantic"), recording whether that signal
# actually surfaced it. Callers combine these flags however they need (e.g.
# for display); a future third signal is added the same way — one more
# independent "found_by_<signal>" flag — with no existing flag or its
# combinations touched.
def rank(
    index_dir: Path,
    query: str,
) -> list[dict[str, object]]:
    manifest = json.loads((index_dir / "manifest.json").read_text(encoding="utf-8"))
    dimension = int(manifest["embedding"]["dimension"])
    model_name = str(manifest["embedding"]["model"])
    embeddings = np.load(index_dir / "embeddings.npy", mmap_mode="r", allow_pickle=False)
    if embeddings.ndim != 2 or embeddings.shape[1] != dimension:
        raise RuntimeError(f"Invalid embedding matrix shape: {embeddings.shape}")

    model = create_model(model_name, dimension, index_dir.parent / "model_cache")
    query_vector = np.asarray(list(model.query_embed([f"query: {query}"]))[0], dtype=np.float32)
    query_vector /= np.linalg.norm(query_vector)
    semantic_scores = np.asarray(embeddings @ query_vector, dtype=np.float32)
    # Every fragment is ranked semantically (no top-N cut-off), so each one
    # always carries a semantic rank: 1 = most similar, len(scores) = least.
    semantic_order = np.argsort(-semantic_scores, kind="stable")
    semantic_rank_by_row = np.empty(len(semantic_scores), dtype=np.int64)
    semantic_rank_by_row[semantic_order] = np.arange(1, len(semantic_scores) + 1)

    connection = sqlite3.connect(index_dir / "index.sqlite3")
    connection.row_factory = sqlite3.Row
    try:
        lexical_rank: dict[int, int] = {}
        lexical = fts_query(query)
        if lexical:
            # Strict phrase match only — no fallback to individual words. If the
            # exact phrase (or, for comma-separated input, none of the exact
            # phrases) isn't found verbatim, this fragment contributes nothing
            # to the lexical signal. Every matching fragment is kept (no LIMIT).
            rows = connection.execute(
                "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts)",
                (lexical,),
            ).fetchall()
            lexical_rank = {int(row["rowid"]): rank for rank, row in enumerate(rows, start=1)}

        results: list[dict[str, object]] = []
        for row in connection.execute("SELECT * FROM chunks"):
            chunk_id = int(row["chunk_id"])
            embedding_row = int(row["embedding_row"])
            semantic_rank = int(semantic_rank_by_row[embedding_row])
            fragment_lexical_rank = lexical_rank.get(chunk_id)
            score = 1.0 / (RRF_K + semantic_rank)
            if fragment_lexical_rank is not None:
                score += 1.0 / (RRF_K + fragment_lexical_rank)
            results.append({
                "chunk_id": chunk_id,
                "hybrid_score": score,
                "semantic_similarity": float(semantic_scores[embedding_row]),
                "lexical_rank": fragment_lexical_rank,
                "found_by_lexical": fragment_lexical_rank is not None,
                # Always True: the semantic ranking covers every fragment.
                "found_by_semantic": True,
                "source_relative_path": row["source_relative_path"],
                "source_absolute_path": row["source_absolute_path"],
                "line_start": row["line_start"],
                "line_end": row["line_end"],
                "heading": row["heading"],
                "text": row["text"],
                "source_sha256": row["source_sha256"],
            })
        results.sort(key=lambda item: item["hybrid_score"], reverse=True)
        return results
    finally:
        connection.close()


# Parse search arguments, execute hybrid ranking, and print human or JSON results.
def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument(
        "--index",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "data" / "hybrid_index",
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    results = rank(args.index.resolve(), args.query)[: max(1, args.limit)]
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    for position, result in enumerate(results, start=1):
        print(f"[{position}] {result['source_relative_path']}:{result['line_start']}-{result['line_end']}")
        if result["heading"]:
            print(f"    {result['heading']}")
        print(
            f"    semantic={result['semantic_similarity']:.4f} "
            f"hybrid={result['hybrid_score']:.6f} "
            f"found_by_lexical={result['found_by_lexical']} "
            f"found_by_semantic={result['found_by_semantic']}"
        )
        preview = re.sub(r"\s+", " ", str(result["text"]))[:500]
        print(f"    {preview}")
        print()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
