#!/usr/bin/env python3
"""Offline hybrid search over the Postgres-backed medical index: pgvector
cosine similarity for the semantic signal, tsvector phrase matching for the
lexical signal, combined with Reciprocal Rank Fusion (RRF)."""

from __future__ import annotations

import argparse
import json
import re
import sys

import numpy as np
from psycopg.rows import namedtuple_row

from medicina_naturista.ai.db import get_pool
from medicina_naturista.ai.embedding_model import cached_query_model
from medicina_naturista.config import settings

# Reciprocal Rank Fusion constant used to combine semantic and lexical ranks
# into hybrid_score (see rank() below). A fragment ranked #1 by both signals
# scores 1/(RRF_K + 1) per signal, so RRF_MAX_SCORE is the highest hybrid_score
# any fragment can ever reach — the fixed ceiling other layers (the UI's
# score-to-percentage display) can rely on without duplicating this constant.
RRF_K = 60.0
RRF_MAX_SCORE = 2.0 / (RRF_K + 1.0)


# Read the embedding model name/dimension the currently-synced index was
# built with (see scripts/build_hybrid_index.py's sync_metadata upsert) —
# the query-time replacement for manifest.json's "embedding" section.
def _embedding_metadata(cursor) -> tuple[str, int]:
    rows = dict(
        cursor.execute(
            "SELECT key, value FROM sync_metadata WHERE key IN ('model_name', 'model_dimension')"
        ).fetchall()
    )
    if "model_name" not in rows or "model_dimension" not in rows:
        raise RuntimeError("Index has not been synced yet (sync_metadata is empty).")
    return rows["model_name"], int(rows["model_dimension"])


# Extract up to 32 words from a text segment, space-joined — the raw phrase
# text handed to Postgres's phraseto_tsquery(), which turns adjacent words
# into a strict "followed by" (<->) tsquery on its own; never build tsquery
# syntax by hand from user text.
def _phrase_words(segment: str) -> str | None:
    words = re.findall(r"[^\W_]+", segment, flags=re.UNICODE)[:32]
    return " ".join(words) if words else None


# Convert user text into the phrase texts a lexical query should OR together:
# comma-separated segments each become one exact-phrase clause (words
# adjacent, in that order); a plain segment yields a single clause. Empty
# segments are dropped. Mirrors the old SQLite FTS5 fts_query()'s behaviour,
# minus the SQL string-building — callers parameterize each phrase text.
def fts_clauses(text: str) -> list[str]:
    segments = text.split(",") if "," in text else [text]
    return [phrase for phrase in (_phrase_words(segment) for segment in segments) if phrase]


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
# When given, BOTH signals are ranked over the filtered subset only (the SQL
# WHERE clause is applied before ROW_NUMBER() computes ranks), not computed
# over the whole index and then filtered: filtering after the fact would
# leave gaps in the rank sequence that skew every fragment's RRF score
# relative to a fresh ranking of just that subset.
def rank(query: str, category_ids: frozenset[str] | None = None) -> list[dict[str, object]]:
    with get_pool().connection() as connection:
        with connection.cursor(row_factory=namedtuple_row) as cursor:
            model_name, dimension = _embedding_metadata(cursor)
            model = cached_query_model(model_name, dimension, settings.model_cache_dir)
            query_vector = np.asarray(list(model.query_embed([f"query: {query}"]))[0], dtype=np.float32)
            query_vector /= np.linalg.norm(query_vector)

            category_filter = ""
            semantic_params: dict[str, object] = {"qvec": query_vector}
            if category_ids:
                category_filter = "WHERE category_id = ANY(%(cats)s)"
                semantic_params["cats"] = list(category_ids)

            # embedding <#> vector = negative inner product; vectors are unit
            # length (see build_hybrid_index.py's embed_chunks()), so the
            # inner product is genuine cosine similarity and ascending <#>
            # order is descending similarity order. No LIMIT: every selected
            # fragment gets a full-range semantic_rank (1 = most similar),
            # matching the exhaustive numpy ranking the old index did.
            semantic_rows = cursor.execute(
                f"""
                SELECT chunk_id, source_relative_path, source_absolute_path, line_start, line_end,
                       heading, text, source_sha256,
                       -(embedding <#> %(qvec)s) AS semantic_similarity,
                       ROW_NUMBER() OVER (ORDER BY embedding <#> %(qvec)s) AS semantic_rank
                FROM chunks
                {category_filter}
                """,
                semantic_params,
            ).fetchall()

            lexical_rank: dict[int, int] = {}
            phrases = fts_clauses(query)
            if phrases:
                # Strict phrase match only — no fallback to individual words.
                # If none of the phrase(s) appear verbatim, this fragment
                # contributes nothing to the lexical signal. Every matching
                # fragment is kept (no LIMIT), ranked by ts_rank_cd with
                # normalization=1 (rank divided by 1+log(document length), so
                # a short focused match outranks the same phrase buried in a
                # much longer document — the closest built-in equivalent to
                # BM25's own length normalization), then renumbered 1.. — so
                # a category filter can never leave gaps in the lexical rank
                # sequence.
                tsquery_sql = " || ".join(["phraseto_tsquery('simple', unaccent(%s))"] * len(phrases))
                lexical_params: list[object] = list(phrases)
                lexical_filter = ""
                if category_ids:
                    lexical_filter = "AND category_id = ANY(%s)"
                    lexical_params.append(list(category_ids))
                lexical_rows = cursor.execute(
                    f"""
                    SELECT chunk_id,
                           ROW_NUMBER() OVER (ORDER BY ts_rank_cd(text_search, query, 1) DESC) AS lexical_rank
                    FROM chunks, (SELECT ({tsquery_sql}) AS query) AS q
                    WHERE text_search @@ query {lexical_filter}
                    """,
                    lexical_params,
                ).fetchall()
                lexical_rank = {row.chunk_id: row.lexical_rank for row in lexical_rows}

    results: list[dict[str, object]] = []
    for row in semantic_rows:
        fragment_lexical_rank = lexical_rank.get(row.chunk_id)
        score = 1.0 / (RRF_K + row.semantic_rank)
        if fragment_lexical_rank is not None:
            score += 1.0 / (RRF_K + fragment_lexical_rank)
        results.append({
            "chunk_id": row.chunk_id,
            "hybrid_score": score,
            "semantic_similarity": float(row.semantic_similarity),
            "lexical_rank": fragment_lexical_rank,
            "found_by_lexical": fragment_lexical_rank is not None,
            "source_relative_path": row.source_relative_path,
            "source_absolute_path": row.source_absolute_path,
            "line_start": row.line_start,
            "line_end": row.line_end,
            "heading": row.heading,
            "text": row.text,
            "source_sha256": row.source_sha256,
        })
    results.sort(key=lambda item: item["hybrid_score"], reverse=True)
    return results


# Parse search arguments, execute hybrid ranking, and print human or JSON results.
def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    results = rank(args.query)
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
