#!/usr/bin/env python3
"""Offline hybrid search over the Postgres-backed medical index: pgvector
cosine similarity for the semantic signal, tsvector prefix matching for the
lexical signal, combined with Reciprocal Rank Fusion (RRF)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence

import numpy as np
from psycopg.rows import namedtuple_row

from medicina_naturista.ai.db import get_pool
from medicina_naturista.ai.embedding_model import cached_query_model
from medicina_naturista.ai.query_terms import GENERIC_QUERY_WORDS, plain
from medicina_naturista.config import settings

# Reciprocal Rank Fusion constant used to combine semantic and lexical ranks
# into hybrid_score (see rank() below). A fragment ranked #1 by both signals
# scores 1/(RRF_K + 1) per signal, so RRF_MAX_SCORE is the highest hybrid_score
# any fragment can ever reach — the fixed ceiling other layers (the UI's
# score-to-percentage display) can rely on without duplicating this constant.
# Three signals feed the fusion: semantic, lexical and heading/path match.
RRF_K = 60.0
RRF_SIGNAL_COUNT = 3
RRF_MAX_SCORE = RRF_SIGNAL_COUNT / (RRF_K + 1.0)

# A fragment's fused score is multiplied by the weight of its PRIORITY (set at
# indexing time, see ai/fragmenter.py): 1 = the document/section is about a
# condition by name, 3 = a section mentions one, 5 = everything else. Every
# weight is <= 1, so RRF_MAX_SCORE stays the ceiling of hybrid_score.
PRIORITY_WEIGHT = {1: 1.0, 3: 0.7, 5: 0.5}

# When the strict (all content words) lexical query matches fewer chunks than
# this, rank() also runs the loose (any content word) query.
MIN_STRICT_LEXICAL_HITS = 10


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


# Words of a text segment, capped at 32 — the raw material of a lexical query.
def _words(segment: str) -> list[str]:
    return re.findall(r"[^\W_]+", segment, flags=re.UNICODE)[:32]


# Prefix stem used for lexical matching. The index is built with the 'simple'
# text-search config (no Romanian stemming), so "genunchi" would never match
# "genunchiului"; matching on a trimmed prefix (`stem:*`) covers the common
# inflections (genunchi/genunchiului, durere/dureri, gripa/gripei) without a
# reindex. Short words keep their full length as prefix.
def _stem(word: str) -> str:
    folded = plain(word)
    return folded[: max(4, len(folded) - 2)] if len(folded) >= 6 else folded


# Content words of a segment: generic words ("pentru", "tratament", ...) and
# one/two-letter fragments are dropped so they cannot make an exact-match
# requirement impossible or flood the OR fallback; if nothing is left (e.g. a
# query made only of short words) every word is kept.
def _content_stems(segment: str) -> list[str]:
    words = _words(segment)
    content = [word for word in words if len(word) >= 3 and plain(word) not in GENERIC_QUERY_WORDS]
    return [_stem(word) for word in (content or words)]


# Convert user text into two tsquery strings for Postgres's to_tsquery():
# `strict` requires every content word of a comma-separated segment (prefix
# match, any order, any distance — segments are OR-ed), `loose` accepts any
# content word and is only used when `strict` finds too little. Stems contain
# letters and digits only, so no tsquery syntax can come from user text.
# `expansions` are alternative names of the condition the query names (see
# ai/conditions.py): each is one more OR-ed all-words group in `strict`, so a
# section titled with a synonym is found too; they are left out of `loose`,
# which must stay narrow. Both are None when the text has no usable word.
def lexical_queries(text: str, expansions: Sequence[str] = ()) -> tuple[str | None, str | None]:
    segments = text.split(",") if "," in text else [text]
    groups = [stems for stems in (_content_stems(segment) for segment in segments) if stems]
    if not groups:
        return None, None
    loose_stems = list(dict.fromkeys(stem for group in groups for stem in group))
    for phrase in expansions:
        stems = _content_stems(phrase)
        if stems and stems not in groups:
            groups.append(stems)
    strict = " | ".join("(" + " & ".join(f"{stem}:*" for stem in group) + ")" for group in groups)
    return strict, " | ".join(f"{stem}:*" for stem in loose_stems)


# (chunk id, raw ts_rank_cd score) pairs matching a to_tsquery() string, best
# first, at most `limit`. ts_rank_cd with normalization=1 divides the rank by
# 1+log(document length), so a short focused match outranks the same words
# buried in a much longer chunk — the closest built-in equivalent to BM25's
# length normalization. Only the order feeds the RRF fusion; the raw score is
# carried along purely so it can be reported.
def _lexical_hits(
    cursor, tsquery: str, category_filter: str, category_params: list[object], limit: int
) -> list[tuple[int, float]]:
    and_category = f"AND {category_filter}" if category_filter else ""
    rows = cursor.execute(
        f"""
        SELECT chunk_id, ts_rank_cd(text_search, query, 1) AS lexical_score
        FROM chunks, (SELECT to_tsquery('simple', unaccent(%s)) AS query) AS q
        WHERE text_search @@ query {and_category}
        ORDER BY lexical_score DESC
        LIMIT %s
        """,
        [tsquery, *category_params, limit],
    ).fetchall()
    return [(row.chunk_id, float(row.lexical_score)) for row in rows]


# Chunk ids whose section heading or file path matches the strict tsquery,
# most similar to the query first, at most `limit`. A chunk sitting under a
# heading that names the condition ("GUTĂ", "Constipație") is the strongest
# hint that it is about that condition, which the body text alone (where the
# word may appear once, in passing) cannot express. Computed at query time
# over heading + path only — short strings, so it costs tens of milliseconds
# without any extra index or reindex.
def _heading_ids(
    cursor, tsquery: str, query_vector, category_filter: str, category_params: list[object], limit: int
) -> list[int]:
    and_category = f"AND {category_filter}" if category_filter else ""
    rows = cursor.execute(
        f"""
        SELECT chunk_id
        FROM chunks
        WHERE to_tsvector('simple', unaccent(heading || ' ' || source_relative_path))
              @@ to_tsquery('simple', unaccent(%s)) {and_category}
        ORDER BY embedding <#> %s
        LIMIT %s
        """,
        [tsquery, *category_params, query_vector, limit],
    ).fetchall()
    return [row.chunk_id for row in rows]


# Combine semantic, lexical and heading rankings with reciprocal rank fusion.
# All signals always run — there is no per-call or per-deployment toggle to turn
# either off. Each contributes at most `limit` candidates (default
# settings.search_candidate_limit): the semantic top-`limit` by cosine
# similarity, the lexical top-`limit` by ts_rank_cd and the heading/path
# matches by similarity. Only the union of the lists is returned, so a search fetches and scores a few hundred rows
# instead of the whole index. A fragment found by only one signal simply gets
# no reciprocal-rank term from the others; its semantic_similarity is still
# reported. Each result carries "found_by_lexical", recording whether the
# lexical query matched it. A future selective signal is added the same way —
# one more independent "found_by_<signal>" flag.
#
# category_ids optionally restricts ranking to chunks whose category_id is
# one of the given ids (see medicina_naturista.ai.categories) — None or an
# empty set means every chunk. When given, BOTH signals are ranked over the
# filtered subset only (the SQL WHERE clause is applied before the ranking
# order is taken), not computed over the whole index and then filtered:
# filtering after the fact would leave gaps in the rank sequence that skew
# every fragment's RRF score relative to a fresh ranking of just that subset.
#
# expansions: alternative names of the condition the query names, which widen
# the lexical and heading signals (the semantic query stays the user's text).
def rank(
    query: str,
    category_ids: frozenset[str] | None = None,
    limit: int | None = None,
    expansions: Sequence[str] = (),
) -> list[dict[str, object]]:
    limit = limit or settings.search_candidate_limit
    with get_pool().connection() as connection:
        with connection.cursor(row_factory=namedtuple_row) as cursor:
            model_name, dimension = _embedding_metadata(cursor)
            model = cached_query_model(model_name, dimension, settings.model_cache_dir)
            query_vector = np.asarray(list(model.query_embed([f"query: {query}"]))[0], dtype=np.float32)
            query_vector /= np.linalg.norm(query_vector)

            category_filter = ""
            category_params: list[object] = []
            if category_ids:
                category_filter = "category_id = ANY(%s)"
                category_params = [list(category_ids)]
            where_category = f"WHERE {category_filter}" if category_filter else ""

            # embedding <#> vector = negative inner product; vectors are unit
            # length (see build_hybrid_index.py's embed_chunks()), so the
            # inner product is genuine cosine similarity and ascending <#>
            # order is descending similarity order. The scan is exact (no
            # ANN index), so the top-`limit` is the true top-`limit`; only
            # the id is read here, the text is fetched for the union below.
            semantic_ids = [
                row.chunk_id
                for row in cursor.execute(
                    f"""
                    SELECT chunk_id FROM chunks
                    {where_category}
                    ORDER BY embedding <#> %s
                    LIMIT %s
                    """,
                    [*category_params, query_vector, limit],
                ).fetchall()
            ]

            lexical_hits: list[tuple[int, float]] = []
            strict, loose = lexical_queries(query, expansions)
            if strict:
                lexical_hits = _lexical_hits(cursor, strict, category_filter, category_params, limit)
                # Too few all-words matches: widen to any content word. The
                # strict matches stay first (they rank above every loose-only
                # match), so this only ever appends candidates.
                if len(lexical_hits) < MIN_STRICT_LEXICAL_HITS and loose != strict:
                    seen = {chunk_id for chunk_id, _ in lexical_hits}
                    extra = [
                        hit
                        for hit in _lexical_hits(cursor, loose, category_filter, category_params, limit)
                        if hit[0] not in seen
                    ]
                    lexical_hits += extra[: limit - len(lexical_hits)]

            heading_ids: list[int] = []
            if strict:
                heading_ids = _heading_ids(cursor, strict, query_vector, category_filter, category_params, limit)

            semantic_rank = {chunk_id: position for position, chunk_id in enumerate(semantic_ids, start=1)}
            lexical_rank = {chunk_id: position for position, (chunk_id, _) in enumerate(lexical_hits, start=1)}
            lexical_score = dict(lexical_hits)
            heading_rank = {chunk_id: position for position, chunk_id in enumerate(heading_ids, start=1)}
            rows = cursor.execute(
                """
                SELECT chunk_id, source_relative_path, source_absolute_path, line_start, line_end,
                       heading, text, source_sha256, priority, conditions,
                       -(embedding <#> %s) AS semantic_similarity
                FROM chunks
                WHERE chunk_id = ANY(%s)
                """,
                [query_vector, list(semantic_rank.keys() | lexical_rank.keys() | heading_rank.keys())],
            ).fetchall()

    results: list[dict[str, object]] = []
    for row in rows:
        fragment_semantic_rank = semantic_rank.get(row.chunk_id)
        fragment_lexical_rank = lexical_rank.get(row.chunk_id)
        fragment_heading_rank = heading_rank.get(row.chunk_id)
        score = 0.0
        if fragment_semantic_rank is not None:
            score += 1.0 / (RRF_K + fragment_semantic_rank)
        if fragment_lexical_rank is not None:
            score += 1.0 / (RRF_K + fragment_lexical_rank)
        if fragment_heading_rank is not None:
            score += 1.0 / (RRF_K + fragment_heading_rank)
        score *= PRIORITY_WEIGHT.get(row.priority, 1.0)
        results.append({
            "chunk_id": row.chunk_id,
            "hybrid_score": score,
            "priority": row.priority,
            "conditions": list(row.conditions),
            "semantic_similarity": float(row.semantic_similarity),
            "lexical_rank": fragment_lexical_rank,
            "lexical_score": lexical_score.get(row.chunk_id),
            "found_by_lexical": fragment_lexical_rank is not None,
            "found_by_heading": fragment_heading_rank is not None,
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
            f"found_by_lexical={result['found_by_lexical']} "
            f"found_by_heading={result['found_by_heading']}"
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
