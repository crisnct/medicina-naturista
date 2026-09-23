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
from pathlib import Path

import numpy as np


def create_model(model_name: str, dimension: int, cache_dir: Path):
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
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


def fts_query(text: str) -> str:
    tokens = re.findall(r"[^\W_]+", text, flags=re.UNICODE)
    return " OR ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens[:32])


def rank(index_dir: Path, query: str, limit: int, candidates: int) -> list[dict[str, object]]:
    manifest = json.loads((index_dir / "manifest.json").read_text(encoding="utf-8"))
    dimension = int(manifest["embedding"]["dimension"])
    model_name = str(manifest["embedding"]["model"])
    embeddings = np.load(index_dir / "embeddings.npy", mmap_mode="r", allow_pickle=False)
    if embeddings.ndim != 2 or embeddings.shape[1] != dimension:
        raise RuntimeError(f"Invalid embedding matrix shape: {embeddings.shape}")

    model = create_model(model_name, dimension, index_dir / "model_cache")
    query_vector = np.asarray(list(model.query_embed([f"query: {query}"]))[0], dtype=np.float32)
    query_vector /= np.linalg.norm(query_vector)
    semantic_scores = np.asarray(embeddings @ query_vector, dtype=np.float32)
    semantic_count = min(candidates, len(semantic_scores))
    semantic_ids = np.argpartition(semantic_scores, -semantic_count)[-semantic_count:]
    semantic_ids = semantic_ids[np.argsort(semantic_scores[semantic_ids])[::-1]]
    semantic_rank = {int(row) + 1: rank for rank, row in enumerate(semantic_ids, start=1)}

    connection = sqlite3.connect(index_dir / "index.sqlite3")
    connection.row_factory = sqlite3.Row
    try:
        lexical_rank: dict[int, int] = {}
        lexical = fts_query(query)
        if lexical:
            rows = connection.execute(
                "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT ?",
                (lexical, candidates),
            ).fetchall()
            lexical_rank = {int(row["rowid"]): rank for rank, row in enumerate(rows, start=1)}

        combined_ids = set(semantic_rank) | set(lexical_rank)
        rrf_k = 60.0
        scores = {
            chunk_id: (1.0 / (rrf_k + semantic_rank[chunk_id]) if chunk_id in semantic_rank else 0.0)
            + (1.0 / (rrf_k + lexical_rank[chunk_id]) if chunk_id in lexical_rank else 0.0)
            for chunk_id in combined_ids
        }
        best_ids = sorted(combined_ids, key=lambda item: scores[item], reverse=True)[:limit]
        if not best_ids:
            return []
        placeholders = ",".join("?" for _ in best_ids)
        rows = connection.execute(
            f"SELECT * FROM chunks WHERE chunk_id IN ({placeholders})", best_ids
        ).fetchall()
        by_id = {int(row["chunk_id"]): row for row in rows}

        results: list[dict[str, object]] = []
        for chunk_id in best_ids:
            row = by_id[chunk_id]
            results.append({
                "chunk_id": chunk_id,
                "hybrid_score": scores[chunk_id],
                "semantic_similarity": float(semantic_scores[int(row["embedding_row"])]),
                "source_relative_path": row["source_relative_path"],
                "source_absolute_path": row["source_absolute_path"],
                "line_start": row["line_start"],
                "line_end": row["line_end"],
                "heading": row["heading"],
                "text": row["text"],
                "source_sha256": row["source_sha256"],
            })
        return results
    finally:
        connection.close()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--index", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--candidates", type=int, default=100)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    results = rank(args.index.resolve(), args.query, max(1, args.limit), max(args.limit, args.candidates))
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    for position, result in enumerate(results, start=1):
        print(f"[{position}] {result['source_relative_path']}:{result['line_start']}-{result['line_end']}")
        if result["heading"]:
            print(f"    {result['heading']}")
        print(f"    semantic={result['semantic_similarity']:.4f} hybrid={result['hybrid_score']:.6f}")
        preview = re.sub(r"\s+", " ", str(result["text"]))[:500]
        print(f"    {preview}")
        print()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
