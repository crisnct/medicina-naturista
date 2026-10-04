#!/usr/bin/env python3
"""Offline search over the Postgres-backed medical index. Every fragment gets
one score that combines the signals the user switched on (A: conditions, B:
lexical, C: semantic); the whole computation runs as a single SQL query (see
rank())."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, replace

import numpy as np
from psycopg.rows import namedtuple_row

from backend.ai.conditions import ResolvedQuery, resolve_query
from backend.ai.db import get_pool
from backend.ai.embedding_model import cached_query_model, get_profile
from backend.ai.query_terms import plain
from backend.config import settings


# The signals of the score, each one a checkbox of the "Căutare avansată" panel:
#   A conditions: P1 / P2 in {0, 1} — a condition the user named is in the
#                 fragment's primary conditions (title) / secondary ones (text)
#   B lexical   : L in [0, 1] — the fraction of the user's comma-separated
#                 expressions that the fragment contains (see lexical_queries())
#   C semantic  : V in [0, 1] — cosine similarity to the message, rescaled from
#                 [median, max] of the search to [0, 1]
# At least one must be on. A signal that is off is not computed at all.
@dataclass(frozen=True)
class SearchSignals:
    conditions: bool = True
    lexical: bool = True
    semantic: bool = True

    def __post_init__(self) -> None:
        if not (self.conditions or self.lexical or self.semantic):
            raise ValueError("At least one search signal must be selected.")

    # The letters of the signals that are on, e.g. "AC" (A conditions, B
    # lexical, C semantic) — also the key of the weights table below.
    @property
    def code(self) -> str:
        flags = (("A", self.conditions), ("B", self.lexical), ("C", self.semantic))
        return "".join(letter for letter, on in flags if on)

    # The inverse of `code`; case-insensitive. Raises ValueError for an empty
    # or unknown code.
    @classmethod
    def from_code(cls, code: str) -> SearchSignals:
        letters = set(code.strip().upper())
        if not letters or not letters <= set("ABC"):
            raise ValueError(f"Search signals must be a non-empty combination of A, B and C, got {code!r}.")
        return cls(conditions="A" in letters, lexical="B" in letters, semantic="C" in letters)


ALL_SIGNALS = SearchSignals()

# score = w_primary*P1 + w_secondary*P2 + w_lexical*L + w_semantic*V, with the
# weights fixed per combination of signals. They keep the priorities in order:
# with every signal on, P1 is worth as much as all the lower ones at their best
# (4 = 2 + 1 + 1) and P2 as much as L plus V (2 = 1 + 1); without L or V the
# weight of P1 is just above P2 plus the remaining one (3 = 2 + 1); with A alone
# a condition in the title outweighs one in the text (2 > 1). Only in the extreme
# tie (a perfect match on everything below) can a lower tier match a higher one.
# L and V weigh the same, so an excellent semantic match can outrank a weak
# lexical one and vice versa.
# (w_primary, w_secondary, w_lexical, w_semantic) by SearchSignals.code.
_WEIGHTS: dict[str, tuple[int, int, int, int]] = {
    "ABC": (4, 2, 1, 1),
    "AB": (3, 2, 1, 0),
    "AC": (3, 2, 0, 1),
    "BC": (0, 0, 1, 1),
    "A": (2, 1, 0, 0),
    "B": (0, 0, 1, 0),
    "C": (0, 0, 0, 1),
}


def weights(signals: SearchSignals) -> tuple[int, int, int, int]:
    return _WEIGHTS[signals.code]


# The signals a search can actually use. The conditions signal needs a condition
# in the message (from the dictionary or identified by the AI, see
# ai/condition_ai.py): without one no fragment can score on it, so it is left out
# and the other signals keep their weights, which makes relevance_percent
# relative to what could contribute (the best fragment can still reach 100%).
# With the conditions signal alone there is nothing else to fall back on and it
# stays (the search then finds nothing).
def effective_signals(signals: SearchSignals, resolved: ResolvedQuery) -> SearchSignals:
    if not signals.conditions or resolved.conditions:
        return signals
    if not (signals.lexical or signals.semantic):
        return signals
    return replace(signals, conditions=False)


# The highest score a fragment can reach with these signals;
# relevance_percent = score / max_score(signals) * 100.
def max_score(signals: SearchSignals) -> int:
    return sum(weights(signals))


# What the evidence text of a fragment adds in front of its indexed text (see
# Retriever._context()): "Secțiune: <heading>" and a blank line. The context
# budget counts the evidence text, so rank() needs the same overhead.
EVIDENCE_HEADING_PREFIX = "Secțiune: "
EVIDENCE_HEADING_SEPARATOR = "\n\n"

# A word shorter than this is matched exactly in a phrase, so "de" does not
# also find "deja" or "despre"; longer ones are matched by prefix.
PREFIX_MATCH_MIN_CHARS = 3


# Words of a text segment, capped at 32 — the raw material of a lexical query.
def _words(segment: str) -> list[str]:
    return re.findall(r"[^\W_]+", segment, flags=re.UNICODE)[:32]


# A word reduced to lowercase letters and digits without diacritics. These are
# the only characters a tsquery operand is built from, so no tsquery syntax can
# come from user text.
def _fold(word: str) -> str:
    return "".join(char for char in plain(word) if char.isalnum())


# Prefix stem used for lexical matching. The index is built with the 'simple'
# text-search config (no Romanian stemming), so "genunchi" would never match
# "genunchiului"; matching on a trimmed prefix (`stem:*`) covers the common
# inflections (genunchi/genunchiului, durere/dureri, gripa/gripei) without a
# reindex. Short words keep their full length as prefix.
def _stem(word: str) -> str:
    folded = _fold(word)
    return folded[: max(4, len(folded) - 2)] if len(folded) >= 6 else folded


def _phrase_operand(word: str) -> str | None:
    folded = _fold(word)
    if not folded:
        return None
    return folded if len(folded) < PREFIX_MATCH_MIN_CHARS else f"{_stem(word)}:*"


# The words of `text`, in the order written and adjacent (the tsquery operator
# `<->`), as one parenthesised phrase; every word counts, generic and short ones
# included. None when `text` has no word.
#   "dureri de picioare" -> "(dure:* <-> de <-> picioa:*)"
def _phrase(text: str) -> str | None:
    operands = [operand for operand in map(_phrase_operand, _words(text)) if operand]
    return "(" + " <-> ".join(operands) + ")" if operands else None


# The lexical queries of a resolved message: one tsquery per comma-separated
# expression (identical expressions count once), so that L is the fraction of
# them a fragment contains. An expression that IS a condition (an exact term or
# a near-identical spelling of one, QuerySegment.whole_condition) is searched
# under every name of the condition, as an OR of their phrases; any other
# expression is searched as written, as one exact phrase — no synonyms, and no
# condition looked up inside it ("gripa la copii" looks for that phrase only,
# even though the conditions signal still recognises Gripa there):
#   "zorbita" -> "(((zorbi:*) | (zorbito:*) | (zorb:* <-> disea:*)))"
# Stems contain letters and digits only, so no tsquery syntax can come from user
# text. Empty when the message has no usable word.
def lexical_queries(resolved: ResolvedQuery) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()
    for segment in resolved.segments:
        key = " ".join(_fold(word) for word in _words(segment.text))
        if not key or key in seen:
            continue
        seen.add(key)
        if segment.whole_condition:
            names = dict.fromkeys(term for condition in segment.conditions for term in condition.terms)
            phrases = list(dict.fromkeys(phrase for phrase in map(_phrase, names) if phrase))
            query = "(" + " | ".join(phrases) + ")" if phrases else None
        else:
            query = _phrase(segment.text)
        if query:
            queries.append(query)
    return queries


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
#   lq / lex  the lexical expressions as tsqueries; the fragments any of them
#             matches (GIN index) with the number of expressions they contain
#   cosine_stats  median/max cosine of THIS search, which is what makes V
#             relative to the search (relevance_percent tells how good a
#             fragment is within this search, not across searches)
#             (all similarities equal, e.g. a one-fragment selection: V = 0)
#   ranked    P1, P2, L = hits / number of expressions, V for every fragment
#   scored    score = w_primary*P1 + w_secondary*P2 + w_lexical*L + w_semantic*V
#   kept      running sum of the evidence characters in score order, over the
#             fragments with score > 0 (a condition, a lexical match or a
#             semantic similarity above the median); only the prefix that fits
#             the budget survives, so the fragments cut from the tail are whole
#             ones, never truncated
# The signals that are off are written as constants (no condition arrays, no
# vector, no tsquery, no statistics), so they cost nothing.
# The text of the kept fragments is read through a LATERAL primary-key lookup, so
# only those few rows are touched: a plain join makes Postgres hash the whole
# table (text included), which was 3-5 times slower.
# There is no candidate limit per signal: nothing is dropped before scoring.
# {condition_columns}, {cosine_column}, {lexical}, {cosine_stats}, {lexical_value}
# and {semantic_value} depend on the signals; {category_where} is an optional
# category filter.
_RANK_SQL = """
WITH
pool AS (
    SELECT chunk_id, char_count, heading,
           {condition_columns},
           {cosine_column}
    FROM chunks
    {category_where}
),
{lexical}
{cosine_stats}
ranked AS (
    SELECT p.chunk_id, p.p1, p.p2, p.cosine, l.hits,
           {lexical_value} AS lexical,
           {semantic_value} AS semantic,
           p.char_count + CASE WHEN btrim(p.heading) <> ''
                               THEN char_length(btrim(p.heading)) + %(heading_overhead)s ELSE 0 END AS evidence_chars
    FROM pool p
    {cosine_join}
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
SELECT k.chunk_id, k.score, k.p1, k.p2, k.lexical, k.semantic, k.cosine, k.hits,
       c.source_relative_path, c.source_absolute_path, c.line_start, c.line_end,
       c.heading, c.text, c.source_sha256, c.business_category,
       c.primary_medical_conditions, c.secondary_medical_conditions
FROM kept k
JOIN LATERAL (SELECT * FROM chunks WHERE chunk_id = k.chunk_id) c ON TRUE
WHERE k.running_chars <= %(max_chars)s
ORDER BY k.score DESC, k.chunk_id
"""

_CONDITION_COLUMNS = """(primary_medical_conditions && %(conditions)s::text[])::int AS p1,
           (secondary_medical_conditions && %(conditions)s::text[])::int AS p2"""
_NO_CONDITION_COLUMNS = "0 AS p1, 0 AS p2"

_COSINE_COLUMN = "-(embedding <#> %(vector)s) AS cosine"
_NO_COSINE_COLUMN = "NULL::double precision AS cosine"
_COSINE_STATS = """cosine_stats AS (
    SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY cosine) AS median, max(cosine) AS peak FROM pool
),"""
_COSINE_JOIN = "CROSS JOIN cosine_stats cs"
_SEMANTIC_VALUE = "greatest(0, least(1, coalesce((p.cosine - cs.median) / nullif(cs.peak - cs.median, 0), 0)))"
_NO_SEMANTIC_VALUE = "0::double precision"

# One tsquery per expression (`lq`, evaluated once), and for every fragment any
# of them matches, how many of them it matches: the OR filter uses the GIN
# index, the count is the numerator of L.
_LEXICAL_CTE = """lq AS MATERIALIZED (
    SELECT to_tsquery('simple', unaccent(expression)) AS query FROM unnest(%(expressions)s::text[]) AS expression
),
lex AS (
    SELECT c.chunk_id, (SELECT count(*) FROM lq WHERE c.text_search @@ lq.query) AS hits
    FROM chunks c
    WHERE c.text_search @@ to_tsquery('simple', unaccent(%(any_expression)s)) {category_and}
),"""
_LEXICAL_VALUE = "coalesce(l.hits, 0)::double precision / %(expression_count)s"
# Lexical signal off, or no usable word in the message: nothing matches lexically.
_NO_LEXICAL_CTE = "lex AS (SELECT NULL::bigint AS chunk_id, NULL::bigint AS hits WHERE FALSE),"
_NO_LEXICAL_VALUE = "0::double precision"


# Score every fragment for `query` and return the ones that fit the context
# budget, best first (ties by chunk_id, so the order is deterministic).
#
# The query is the user's message. `signals` picks what the score is made of
# (see SearchSignals and _WEIGHTS); the signals that are off are not computed,
# in particular the question is not embedded without the semantic signal. A
# fragment with score 0 is not returned. The conditions the message names (see
# ai/conditions.py; each comma-separated expression is recognised on its own)
# decide P1/P2; the lexical signal looks for each expression on its own (see
# lexical_queries()); the semantic signal uses the message as typed. `resolved`
# is the message already resolved (the dictionary's conditions completed with
# the ones the AI identified, see condition_ai.resolved_for()); without it the
# message is resolved against the dictionary alone.
# Without any condition in the message the conditions signal is dropped (see
# effective_signals()); the results carry the signals actually used.
#
# category_ids optionally restricts the search to chunks whose category_id is
# one of the given ids (see backend.ai.categories) — None or an
# empty set means every chunk. The filter is applied before the search
# statistics (median cosine), so V stays relative to the fragments the user
# actually searches in.
#
# max_chars is the evidence budget (the AI provider's context limit): the
# results are the highest-scored prefix whose evidence text fits in it. None
# means no budget: every fragment is returned.
#
# Each result carries the fields of the signals that are on; those of a signal
# that is off (condition_in_*, lexical_score, semantic_*) are None.
# Budget used when the caller sets none (fits Postgres bigint).
UNLIMITED_CHARS = 2**62


def rank(
    query: str,
    category_ids: frozenset[str] | None = None,
    max_chars: int | None = None,
    signals: SearchSignals = ALL_SIGNALS,
    resolved: ResolvedQuery | None = None,
) -> list[dict[str, object]]:
    query = " ".join(query.split())
    if not query:
        return []
    if resolved is None:
        resolved = resolve_query(query)
    if not resolved.segments:  # no word at all, e.g. "?!": nothing to search for
        return []
    signals = effective_signals(signals, resolved)
    condition_names = list(resolved.condition_names) if signals.conditions else []
    expressions = lexical_queries(resolved) if signals.lexical else []
    # Every signal that is on has nothing to look for (e.g. only the conditions
    # signal and no condition in the message): no fragment can score.
    if not (condition_names or expressions or signals.semantic):
        return []

    category_where = "WHERE category_id = ANY(%(categories)s)" if category_ids else ""
    category_and = "AND c.category_id = ANY(%(categories)s)" if category_ids else ""
    sql = _RANK_SQL.format(
        condition_columns=_CONDITION_COLUMNS if signals.conditions else _NO_CONDITION_COLUMNS,
        cosine_column=_COSINE_COLUMN if signals.semantic else _NO_COSINE_COLUMN,
        category_where=category_where,
        lexical=_LEXICAL_CTE.format(category_and=category_and) if expressions else _NO_LEXICAL_CTE,
        cosine_stats=_COSINE_STATS if signals.semantic else "",
        cosine_join=_COSINE_JOIN if signals.semantic else "",
        lexical_value=_LEXICAL_VALUE if expressions else _NO_LEXICAL_VALUE,
        semantic_value=_SEMANTIC_VALUE if signals.semantic else _NO_SEMANTIC_VALUE,
    )

    w_primary, w_secondary, w_lexical, w_semantic = weights(signals)
    parameters: dict[str, object] = {
        "conditions": condition_names,
        "expressions": expressions,
        "any_expression": " | ".join(expressions),
        "expression_count": len(expressions),
        "categories": list(category_ids) if category_ids else None,
        "heading_overhead": len(EVIDENCE_HEADING_PREFIX) + len(EVIDENCE_HEADING_SEPARATOR),
        "w_primary": w_primary,
        "w_secondary": w_secondary,
        "w_lexical": w_lexical,
        "w_semantic": w_semantic,
        "max_chars": max_chars if max_chars is not None else UNLIMITED_CHARS,
    }
    with get_pool().connection() as connection:
        with connection.cursor(row_factory=namedtuple_row) as cursor:
            if signals.semantic:
                model_name, dimension = _embedding_metadata(cursor)
                # The profile of the model the index was built with decides how the
                # question is written (prefix / instruction) and its vector width.
                profile = get_profile(model_name)
                if profile.dimension != dimension:
                    raise RuntimeError(
                        f"Index dimension {dimension} does not match model {model_name} ({profile.dimension})."
                    )
                model = cached_query_model(model_name, settings.model_cache_dir)
                # Unit-length vector: the inner product with the (also unit-length,
                # see build_hybrid_index.py's embed_chunks()) fragment vectors is
                # the cosine similarity. The scan is exact, so V is exact too.
                vector = np.asarray(list(model.query_embed([profile.query_text(query)]))[0], dtype=np.float32)
                vector /= np.linalg.norm(vector)
                parameters["vector"] = vector
            rows = cursor.execute(sql, parameters).fetchall()

    return [
        {
            "chunk_id": row.chunk_id,
            "score": float(row.score),
            "condition_in_title": bool(row.p1) if signals.conditions else None,
            "condition_in_text": bool(row.p2) if signals.conditions else None,
            "lexical_score": float(row.lexical) if row.hits is not None else None,
            "semantic_score": float(row.semantic) if signals.semantic else None,
            "semantic_similarity": float(row.cosine) if signals.semantic else None,
            "found_by_lexical": row.hits is not None,
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
            "signals": signals,
        }
        for row in rows
    ]


# Run one throwaway search so the first real one is fast: it loads the
# embedding model and the condition dictionary and pulls the index into
# Postgres's buffers. All signals are on, so the model is loaded too.
def warm_up() -> None:
    rank("gripa", max_chars=1, signals=ALL_SIGNALS)


# Parse search arguments, execute the search, and print human or JSON results.
def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--signals",
        default=ALL_SIGNALS.code,
        help="signals to score with: any combination of A (conditions), B (lexical), C (semantic); default ABC",
    )
    args = parser.parse_args()
    try:
        signals = SearchSignals.from_code(args.signals)
    except ValueError as exc:
        parser.error(str(exc))
    results = rank(args.query, signals=signals)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2, default=lambda value: value.code))
        return
    for position, result in enumerate(results, start=1):
        print(f"[{position}] {result['source_relative_path']}:{result['line_start']}-{result['line_end']}")
        if result["heading"]:
            print(f"    {result['heading']}")
        print(
            f"    score={result['score']:.3f} "
            f"P1={int(bool(result['condition_in_title']))} P2={int(bool(result['condition_in_text']))} "
            f"L={result['lexical_score'] or 0.0:.3f} V={result['semantic_score'] or 0.0:.3f} "
            f"cosine={result['semantic_similarity'] or 0.0:.4f}"
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
