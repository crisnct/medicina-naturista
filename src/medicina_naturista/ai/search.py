#!/usr/bin/env python3
"""Offline search over the Postgres-backed medical index. Every fragment gets
one score that combines four signals in strict priority order (P1 > P2 > P3 >
P4); the whole computation runs as a single SQL query (see rank())."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence

import numpy as np
from psycopg.rows import namedtuple_row

from medicina_naturista.ai.conditions import ResolvedQuery, resolve_query
from medicina_naturista.ai.db import get_pool
from medicina_naturista.ai.embedding_model import cached_query_model
from medicina_naturista.ai.query_terms import GENERIC_QUERY_WORDS, plain
from medicina_naturista.config import settings

# score = 8*P1 + 4*P2 + 2*L + 1*V, with P1/P2 in {0, 1} and L/V in [0, 1].
#   P1: a condition the user named is in the fragment's primary conditions (title)
#   P2: a condition the user named is in the fragment's secondary conditions (text)
#   L : lexical score, relative to the best lexical match of the search
#   V : semantic similarity, rescaled from [median, max] of the search to [0, 1]
# The weights make the priorities strict where it matters: P1 beats every
# combination of the lower signals (8 > 4 + 2 + 1) and P2 beats lexical plus
# semantic (4 > 2 + 1). P3 vs P4 is deliberately soft: lexical counts double, so
# an excellent semantic match can still outrank a weak lexical one.
WEIGHT_PRIMARY = 8
WEIGHT_SECONDARY = 4
WEIGHT_LEXICAL = 2
WEIGHT_SEMANTIC = 1
# The highest score a fragment can reach; relevance_percent = score / MAX_SCORE.
MAX_SCORE = WEIGHT_PRIMARY + WEIGHT_SECONDARY + WEIGHT_LEXICAL + WEIGHT_SEMANTIC

# What the evidence text of a fragment adds in front of its indexed text (see
# Retriever._context()): "Secțiune: <heading>" and a blank line. The context
# budget counts the evidence text, so rank() needs the same overhead.
EVIDENCE_HEADING_PREFIX = "Secțiune: "
EVIDENCE_HEADING_SEPARATOR = "\n\n"


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
# requirement impossible. With `keep_all_if_empty`, a segment made only of such
# words (e.g. a query of short words) keeps every word instead of nothing.
def _content_stems(segment: str, keep_all_if_empty: bool = True) -> list[str]:
    words = _words(segment)
    content = [word for word in words if len(word) >= 3 and plain(word) not in GENERIC_QUERY_WORDS]
    return [_stem(word) for word in (content or (words if keep_all_if_empty else []))]


def _and_group(stems: Sequence[str]) -> str:
    return "(" + " & ".join(f"{stem}:*" for stem in stems) + ")"


# The lexical tsquery of a resolved message. Segments (the comma-separated
# expressions) are OR-ed; the content words of one segment are AND-ed, in any
# order and at any distance, each as a prefix match. Where a segment names a
# condition, that condition's name is replaced by an OR of all its names and
# synonyms, and the other words of the segment stay AND-ed with it:
#   "tratament pentru gripa la copii" ->
#   (tratame:* & copii:* & ((gripa:*) | (influen:*) | (season:* & flu:*) | ...))
# So a synonym never lets a fragment skip the other words the user wrote.
# Stems contain letters and digits only, so no tsquery syntax can come from user
# text. None when the message has no usable word.
def lexical_query(resolved: ResolvedQuery) -> str | None:
    groups: list[str] = []
    for segment in resolved.segments:
        if not segment.conditions:
            stems = _content_stems(segment.text)
            if stems:
                groups.append(_and_group(stems))
            continue
        rest = _content_stems(segment.remainder, keep_all_if_empty=False)
        names = dict.fromkeys(term for condition in segment.conditions for term in condition.terms)
        alternatives = list(dict.fromkeys(
            _and_group(stems) for stems in (_content_stems(term) for term in names) if stems
        ))
        parts = [f"{stem}:*" for stem in rest]
        if alternatives:
            parts.append("(" + " | ".join(alternatives) + ")")
        if parts:
            groups.append("(" + " & ".join(parts) + ")")
    return " | ".join(groups) or None


# Read the embedding model name/dimension the currently-synced index was
# built with (see scripts/build_hybrid_index.py's sync_metadata upsert).
def _embedding_metadata(cursor) -> tuple[str, int]:
    rows = dict(
        cursor.execute(
            "SELECT key, value FROM sync_metadata WHERE key IN ('model_name', 'model_dimension')"
        ).fetchall()
    )
    if "model_name" not in rows or "model_dimension" not in rows:
        raise RuntimeError("Index has not been synced yet (sync_metadata is empty).")
    return rows["model_name"], int(rows["model_dimension"])


# The whole search as ONE query, so Postgres does every step next to the data:
#   pool      every fragment of the selected categories: P1/P2 from the indexed
#             condition arrays and the exact cosine similarity to the query
#   lex       the fragments the tsquery matches (GIN index) with their ts_rank_cd
#   *_stats   median/max cosine and best lexical rank of THIS search, which is
#             what makes L and V relative to the search (relevance_percent tells
#             how good a fragment is within this search, not across searches)
#             (all similarities equal, e.g. a one-fragment selection: V = 0)
#   scored    score = 8*P1 + 4*P2 + 2*L + V for every fragment
#   kept      running sum of the evidence characters in score order, over the
#             fragments with score > 0 (a condition, a lexical match or a
#             semantic similarity above the median); only the prefix that fits
#             the budget survives, so the fragments cut from the tail are whole
#             ones, never truncated
# The text of the kept fragments is read through a LATERAL primary-key lookup, so
# only those few rows are touched: a plain join makes Postgres hash the whole
# table (text included), which was 3-5 times slower.
# There is no candidate limit per signal: nothing is dropped before scoring.
# ts_rank_cd normalization 1 divides by 1 + log(document length), so a short
# focused fragment outranks the same words buried in a very long one.
# {lexical} is the `lex` CTE, {category_where} an optional category filter.
_RANK_SQL = """
WITH
pool AS (
    SELECT chunk_id, char_count, heading,
           (primary_medical_conditions && %(conditions)s::text[])::int AS p1,
           (secondary_medical_conditions && %(conditions)s::text[])::int AS p2,
           -(embedding <#> %(vector)s) AS cosine
    FROM chunks
    {category_where}
),
{lexical},
cosine_stats AS (
    SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY cosine) AS median, max(cosine) AS peak FROM pool
),
lexical_stats AS (SELECT max(raw) AS peak FROM lex),
ranked AS (
    SELECT p.chunk_id, p.p1, p.p2, p.cosine, l.raw,
           coalesce(l.raw / nullif(ls.peak, 0), 0) AS lexical,
           greatest(0, least(1, coalesce((p.cosine - cs.median) / nullif(cs.peak - cs.median, 0), 0))) AS semantic,
           p.char_count + CASE WHEN btrim(p.heading) <> ''
                               THEN char_length(btrim(p.heading)) + %(heading_overhead)s ELSE 0 END AS evidence_chars
    FROM pool p
    CROSS JOIN cosine_stats cs
    CROSS JOIN lexical_stats ls
    LEFT JOIN lex l USING (chunk_id)
),
scored AS (
    SELECT *, %(w_primary)s * p1 + %(w_secondary)s * p2 + %(w_lexical)s * lexical + %(w_semantic)s * semantic AS score
    FROM ranked
),
kept AS (
    SELECT *, sum(evidence_chars) OVER (ORDER BY score DESC, chunk_id ROWS UNBOUNDED PRECEDING) AS running_chars
    FROM scored
    WHERE score > 0
)
SELECT k.chunk_id, k.score, k.p1, k.p2, k.lexical, k.semantic, k.cosine, k.raw,
       c.source_relative_path, c.source_absolute_path, c.line_start, c.line_end,
       c.heading, c.text, c.source_sha256, c.business_category,
       c.primary_medical_conditions, c.secondary_medical_conditions
FROM kept k
JOIN LATERAL (SELECT * FROM chunks WHERE chunk_id = k.chunk_id) c ON TRUE
WHERE k.running_chars <= %(max_chars)s
ORDER BY k.score DESC, k.chunk_id
"""

_LEXICAL_CTE = """lex AS (
    SELECT chunk_id, ts_rank_cd(text_search, to_tsquery('simple', unaccent(%(tsquery)s)), 1) AS raw
    FROM chunks
    WHERE text_search @@ to_tsquery('simple', unaccent(%(tsquery)s)) {category_and}
)"""
# No usable word in the message: nothing matches lexically.
_NO_LEXICAL_CTE = "lex AS (SELECT NULL::bigint AS chunk_id, NULL::real AS raw WHERE FALSE)"


# Score every fragment for `query` and return the ones that fit the context
# budget, best first (ties by chunk_id, so the order is deterministic).
#
# The query is the user's message. The conditions it names (see
# ai/conditions.py; each comma-separated expression is recognised on its own)
# decide P1/P2, and their synonyms widen the lexical signal; the semantic
# signal uses the message as typed.
#
# category_ids optionally restricts the search to chunks whose category_id is
# one of the given ids (see medicina_naturista.ai.categories) — None or an
# empty set means every chunk. The filter is applied before the search
# statistics (median cosine, best lexical rank), so L and V stay relative to
# the fragments the user actually searches in.
#
# max_chars is the evidence budget (the AI provider's context limit): the
# results are the highest-scored prefix whose evidence text fits in it. None
# means no budget: every fragment is returned.
# Budget used when the caller sets none (fits Postgres bigint).
UNLIMITED_CHARS = 2**62


def rank(
    query: str,
    category_ids: frozenset[str] | None = None,
    max_chars: int | None = None,
) -> list[dict[str, object]]:
    query = " ".join(query.split())
    if not query:
        return []
    resolved = resolve_query(query)
    if not resolved.segments:  # no word at all, e.g. "?!": nothing to search for
        return []
    tsquery = lexical_query(resolved)
    category_where = "WHERE category_id = ANY(%(categories)s)" if category_ids else ""
    category_and = "AND category_id = ANY(%(categories)s)" if category_ids else ""
    lexical = _LEXICAL_CTE.format(category_and=category_and) if tsquery else _NO_LEXICAL_CTE
    sql = _RANK_SQL.format(category_where=category_where, lexical=lexical)

    with get_pool().connection() as connection:
        with connection.cursor(row_factory=namedtuple_row) as cursor:
            model_name, dimension = _embedding_metadata(cursor)
            model = cached_query_model(model_name, dimension, settings.model_cache_dir)
            # Unit-length vector: the inner product with the (also unit-length,
            # see build_hybrid_index.py's embed_chunks()) fragment vectors is
            # the cosine similarity. The scan is exact, so V is exact too.
            vector = np.asarray(list(model.query_embed([f"query: {query}"]))[0], dtype=np.float32)
            vector /= np.linalg.norm(vector)
            rows = cursor.execute(
                sql,
                {
                    "conditions": list(resolved.condition_names),
                    "vector": vector,
                    "tsquery": tsquery,
                    "categories": list(category_ids) if category_ids else None,
                    "heading_overhead": len(EVIDENCE_HEADING_PREFIX) + len(EVIDENCE_HEADING_SEPARATOR),
                    "w_primary": WEIGHT_PRIMARY,
                    "w_secondary": WEIGHT_SECONDARY,
                    "w_lexical": WEIGHT_LEXICAL,
                    "w_semantic": WEIGHT_SEMANTIC,
                    "max_chars": max_chars if max_chars is not None else UNLIMITED_CHARS,
                },
            ).fetchall()

    return [
        {
            "chunk_id": row.chunk_id,
            "score": float(row.score),
            "condition_in_title": bool(row.p1),
            "condition_in_text": bool(row.p2),
            "lexical_score": float(row.lexical) if row.raw is not None else None,
            "semantic_score": float(row.semantic),
            "semantic_similarity": float(row.cosine),
            "found_by_lexical": row.raw is not None,
            "business_category": row.business_category,
            "primary_medical_conditions": list(row.primary_medical_conditions),
            "secondary_medical_conditions": list(row.secondary_medical_conditions),
            "source_relative_path": row.source_relative_path,
            "source_absolute_path": row.source_absolute_path,
            "line_start": row.line_start,
            "line_end": row.line_end,
            "heading": row.heading,
            "text": row.text,
            "source_sha256": row.source_sha256,
        }
        for row in rows
    ]


# Run one throwaway search so the first real one is fast: it loads the
# embedding model and the condition dictionary and pulls the index into
# Postgres's buffers.
def warm_up() -> None:
    rank("gripa", max_chars=1)


# Parse search arguments, execute the search, and print human or JSON results.
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
            f"    score={result['score']:.3f} "
            f"P1={int(result['condition_in_title'])} P2={int(result['condition_in_text'])} "
            f"L={result['lexical_score'] or 0.0:.3f} V={result['semantic_score']:.3f} "
            f"cosine={result['semantic_similarity']:.4f}"
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
