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
# formula. The semantic ranking covers every fragment, so only the lexical
# signal is selective: each result carries "found_by_lexical", recording
# whether the exact phrase matched it. A future selective signal is added the
# same way — one more independent "found_by_<signal>" flag.
#
# category_ids optionally restricts ranking to chunks whose category_id is
# one of the given ids (see medicina_naturista.ai.categories) — None or an
# empty set means every chunk, matching the pre-category behaviour exactly.
# When given, BOTH signals are ranked over the filtered subset only, not
# computed over the whole index and then filtered: filtering after the fact
# would leave gaps in the rank sequence (e.g. semantic ranks 1, 4, 9, ...)
# that skew every fragment's RRF score relative to a fresh ranking of just
# that subset. Excluded chunks must never affect the ranks assigned to kept
# ones.
def rank(
    index_dir: Path,
    query: str,
    category_ids: frozenset[str] | None = None,
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

    connection = sqlite3.connect(index_dir / "index.sqlite3")
    connection.row_factory = sqlite3.Row
    try:
        if category_ids:
            placeholders = ",".join("?" for _ in category_ids)
            chunk_rows = connection.execute(
                f"SELECT * FROM chunks WHERE category_id IN ({placeholders})",
                tuple(category_ids),
            ).fetchall()
        else:
            chunk_rows = connection.execute("SELECT * FROM chunks").fetchall()
        allowed_chunk_ids = {int(row["chunk_id"]) for row in chunk_rows} if category_ids else None

        # Semantic ranking runs only over the rows selected above: fancy-index
        # the embedding matrix down to that subset (a full-index unfiltered
        # query skips this entirely and reuses the original mmap array).
        if category_ids:
            embedding_rows = np.asarray([row["embedding_row"] for row in chunk_rows], dtype=np.int64)
            subset_embeddings = embeddings[embedding_rows]
        else:
            subset_embeddings = embeddings
        subset_scores = np.asarray(subset_embeddings @ query_vector, dtype=np.float32)
        # Every selected fragment is ranked semantically (no top-N cut-off), so
        # each one always carries a semantic rank: 1 = most similar within the
        # selected subset, len(subset) = least.
        subset_order = np.argsort(-subset_scores, kind="stable")
        semantic_rank_by_position = np.empty(len(subset_scores), dtype=np.int64)
        semantic_rank_by_position[subset_order] = np.arange(1, len(subset_scores) + 1)

        lexical_rank: dict[int, int] = {}
        lexical = fts_query(query)
        if lexical:
            # Strict phrase match only — no fallback to individual words. If the
            # exact phrase (or, for comma-separated input, none of the exact
            # phrases) isn't found verbatim, this fragment contributes nothing
            # to the lexical signal. Every matching fragment is kept (no LIMIT).
            # Matches outside the category filter are skipped, and the kept
            # ones are renumbered 1.. in their original (bm25) order, so the
            # lexical rank sequence has no gaps left by the skipped rows.
            fts_rows = connection.execute(
                "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts)",
                (lexical,),
            ).fetchall()
            next_lexical_rank = 1
            for fts_row in fts_rows:
                chunk_id = int(fts_row["rowid"])
                if allowed_chunk_ids is not None and chunk_id not in allowed_chunk_ids:
                    continue
                lexical_rank[chunk_id] = next_lexical_rank
                next_lexical_rank += 1

        results: list[dict[str, object]] = []
        for position, row in enumerate(chunk_rows):
            chunk_id = int(row["chunk_id"])
            semantic_rank = int(semantic_rank_by_position[position])
            fragment_lexical_rank = lexical_rank.get(chunk_id)
            score = 1.0 / (RRF_K + semantic_rank)
            if fragment_lexical_rank is not None:
                score += 1.0 / (RRF_K + fragment_lexical_rank)
            results.append({
                "chunk_id": chunk_id,
                "hybrid_score": score,
                "semantic_similarity": float(subset_scores[position]),
                "lexical_rank": fragment_lexical_rank,
                "found_by_lexical": fragment_lexical_rank is not None,
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
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    results = rank(args.index.resolve(), args.query)
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
            f"found_by_lexical={result['found_by_lexical']}"
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
