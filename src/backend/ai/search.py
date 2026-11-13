#!/usr/bin/env python3
"""Offline search over the Postgres-backed medical index. Every fragment gets
one score that combines the signals the user switched on (A: conditions, B:
lexical, C: semantic); the whole computation runs as a single SQL query (see
rank())."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass, replace

import numpy as np
from psycopg.rows import namedtuple_row

from backend.ai.conditions import ResolvedQuery, load_dictionary, resolve_query
from backend.ai.embedding_model import cached_query_model, get_profile
from backend.ai.index_state import index_reader
from backend.ai.query_terms import plain
from backend.config import settings
from backend.core.language import Language, current_language, language_scope, validate_language
from backend.core.score_formula import compile_search_formula, search_formula_sql


# The signals of the score, each one a checkbox of the "Căutare avansată" panel:
#   A conditions: P1 / P2 in {0, 1} — a condition the user named is in the
#                 fragment's primary conditions (title) / secondary ones (text)
#   B lexical   : L in [0, 1] — BM25 of the fragment for the user's comma-separated
#                 expressions, relative to the best fragment of the search (see
#                 lexical_query())
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
    # lexical, C semantic).
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
            raise ValueError(
                f"Search signals must be a non-empty combination of A, B and C, got {code!r}."
            )
        return cls(conditions="A" in letters, lexical="B" in letters, semantic="C" in letters)


ALL_SIGNALS = SearchSignals()

# The score of a fragment is the operator's formula (SEARCH_SCORE_FORMULA in .env, default
# 4*P1 + 2*P2 + L + V; grammar and checks in core/score_formula.py) over four numbers:
# P1 and P2 in {0, 1}, L and V in [0, 1]. A signal that is off is 0 in the formula, so the
# same formula serves every combination. The default keeps the priorities in order: P1 is
# worth as much as all the lower ones at their best (4 = 2 + 1 + 1) and P2 as much as L
# plus V (2 = 1 + 1), so only in the extreme tie (a perfect match on everything below) can
# a lower tier match a higher one; L and V weigh the same.
_SCORE_COLUMNS = {"P1": "p1", "P2": "p2", "L": "lexical", "V": "semantic"}


# The formula as a SQL expression over the columns of the `ranked` CTE.
def score_sql() -> str:
    return search_formula_sql(settings.search_score_formula, _SCORE_COLUMNS)


# The signals a search can actually use. The conditions signal needs a condition
# in the message (from the dictionary or identified by the AI, see
# ai/condition_ai.py): without one no fragment can score on it, so it is left out
# and the other signals keep their place in the formula, which makes relevance_percent
# relative to what could contribute (the best fragment can still reach 100%).
# With the conditions signal alone there is nothing else to fall back on and it
# stays (the search then finds nothing).
def effective_signals(signals: SearchSignals, resolved: ResolvedQuery) -> SearchSignals:
    if not signals.conditions or resolved.conditions:
        return signals
    if not (signals.lexical or signals.semantic):
        return signals
    return replace(signals, conditions=False)


# The highest score a fragment can reach with these signals: the formula with every signal
# that is on at its maximum and the others at 0; relevance_percent = score / max_score * 100.
def max_score(signals: SearchSignals) -> float:
    on = (
        float(signals.conditions),
        float(signals.conditions),
        float(signals.lexical),
        float(signals.semantic),
    )
    return compile_search_formula(settings.search_score_formula)(*on)


# What the evidence text of a fragment adds in front of its indexed text (see
# Retriever._context()): "Secțiune: <heading>" and a blank line. The context
# budget counts the evidence text, so rank() needs the same overhead.
EVIDENCE_HEADING_PREFIX = "Secțiune: "
EVIDENCE_HEADING_SEPARATOR = "\n\n"


def evidence_heading_prefix() -> str:
    return "Section: " if current_language() == "en" else EVIDENCE_HEADING_PREFIX


# Words of a text segment, capped at 32 — the raw material of a lexical query.
def _words(segment: str) -> list[str]:
    return re.findall(r"[^\W_]+", segment, flags=re.UNICODE)[:32]


# A word reduced to lowercase letters and digits without diacritics; two expressions
# with the same folded words are the same expression.
def _fold(word: str) -> str:
    return "".join(char for char in plain(word) if char.isalnum())


# How the lexical signal (BM25, ParadeDB pg_search) reads a question. Every expression
# (the question split at commas, identical ones counted once) becomes one query, and
# a fragment's BM25 is the sum over the expressions it matches. The words are analysed
# by the index itself (language stemmer, lowercase, diacritics folded), so none of that
# is done here, and the user's text only ever travels as a bound parameter.
#   * a plain expression: the share of its words (TERMS_MATCH_FRACTION, rounded up) in
#     any order, or the words as a phrase (up to PHRASE_SLOP words in between), which
#     scores PHRASE_BOOST times more; found in the heading it scores HEADING_BOOST
#     times more than in the text.
#   * an expression that IS a condition (QuerySegment.whole_condition, an exact term or
#     a near-identical spelling of one): every name of the condition as a phrase.
# The index has one stemmer per language (idx_chunks_bm25, migration 044).
TERMS_MATCH_FRACTION = 0.75
PHRASE_SLOP = 1
PHRASE_BOOST = 2
HEADING_BOOST = 2
_FIELD_LANGUAGES = ("ro", "en")


class _Parameters:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    # Bind `value` and return its placeholder; the cast keeps ARRAY[...] unambiguous.
    def text(self, value: str) -> str:
        name = f"lexical_{len(self.values)}"
        self.values[name] = value
        return f"%({name})s::text"


def _terms_clause(field: str, words: list[str], parameters: _Parameters) -> str:
    by_fold: dict[str, str] = {}
    for word in words:
        if folded := _fold(word):
            by_fold.setdefault(folded, word)
    terms = list(by_fold.values())
    required = max(1, math.ceil(len(terms) * TERMS_MATCH_FRACTION))
    matches = ", ".join(f"paradedb.match('{field}', {parameters.text(term)})" for term in terms)
    return f"paradedb.boolean(should => ARRAY[{matches}], minimum_should_match => {required})"


def _phrase_clause(field: str, words: list[str], slop: int, parameters: _Parameters) -> str:
    if len(words) == 1:
        return f"paradedb.match('{field}', {parameters.text(words[0])})"
    items = ", ".join(parameters.text(word) for word in words)
    return f"paradedb.phrase('{field}', ARRAY[{items}], {slop})"


# The clauses one expression is searched with in one field (text or heading).
def _field_clauses(field: str, segment, parameters: _Parameters) -> list[str]:
    if segment.whole_condition:
        names = dict.fromkeys(term for condition in segment.conditions for term in condition.terms)
        phrases = [_words(name) for name in names]
        return [_phrase_clause(field, words, 0, parameters) for words in phrases if words]
    words = _words(segment.text)
    if not words:
        return []
    clauses = [_terms_clause(field, words, parameters)]
    if len(words) > 1:
        phrase = _phrase_clause(field, words, PHRASE_SLOP, parameters)
        clauses.append(f"paradedb.boost({PHRASE_BOOST}, {phrase})")
    return clauses


# For highlighting: the words of the expressions the lexical query searches by their words
# (the expressions that are not a condition) and the canonical names of the conditions it
# searches by all their names (the expressions that are a condition).
def lexical_terms(resolved: ResolvedQuery) -> tuple[list[str], set[str]]:
    words: list[str] = []
    names: set[str] = set()
    for segment in resolved.segments:
        if segment.whole_condition:
            names.update(condition.name for condition in segment.conditions)
        else:
            words.extend(_words(segment.text))
    return list(dict.fromkeys(words)), names


# The lexical query of a resolved message and its parameters, or None when the
# message has no usable word.
def lexical_query(resolved: ResolvedQuery) -> tuple[str, dict[str, object]] | None:
    language = current_language()
    if language not in _FIELD_LANGUAGES:
        raise ValueError(f"Unsupported lexical language {language!r}.")
    parameters = _Parameters()
    expressions: list[str] = []
    seen: set[str] = set()
    for segment in resolved.segments:
        key = " ".join(_fold(word) for word in _words(segment.text))
        if not key or key in seen:
            continue
        seen.add(key)
        in_text = _field_clauses(f"text_{language}", segment, parameters)
        in_heading = _field_clauses(f"heading_{language}", segment, parameters)
        clauses = in_text + [f"paradedb.boost({HEADING_BOOST}, {clause})" for clause in in_heading]
        if clauses:
            expressions.append(f"paradedb.boolean(should => ARRAY[{', '.join(clauses)}])")
    if not expressions:
        return None
    return f"paradedb.boolean(should => ARRAY[{', '.join(expressions)}])", parameters.values


# The whole search as ONE query, so Postgres does every step next to the data:
#   pool      every fragment of the selected categories: P1/P2 from the indexed
#             condition arrays and the exact cosine similarity to the query
#   lex       the fragments the BM25 index finds for the lexical query (see
#             lexical_query()) with their BM25 score, and lex_stats the best one
#   cosine_stats  median/max cosine of THIS search, which is what makes V
#             relative to the search (relevance_percent tells how good a
#             fragment is within this search, not across searches)
#             (all similarities equal, e.g. a one-fragment selection: V = 0)
#   ranked    P1, P2, L = BM25 / the best BM25 of THIS search, V for every fragment
#   scored    score = the score formula over P1, P2, L, V (see score_sql())
#   kept      running sum of the evidence characters in score order, over the
#             fragments with score > 0 (a condition, a lexical match or a
#             semantic similarity above the median); only the prefix that fits
#             the budget survives, so the fragments cut from the tail are whole
#             ones, never truncated
# The signals that are off are written as constants (no condition arrays, no
# vector, no BM25 query, no statistics), so they cost nothing.
# The text of the kept fragments is read through a LATERAL primary-key lookup, so
# only those few rows are touched: a plain join makes Postgres hash the whole
# table (text included), which was 3-5 times slower.
# There is no candidate limit per signal: nothing is dropped before scoring.
# {condition_columns}, {cosine_column}, {lexical}, {cosine_stats}, {lexical_join},
# {lexical_value} and {semantic_value} depend on the signals, {score} on the formula; {category_where} is an optional
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
    SELECT p.chunk_id, p.p1, p.p2, p.cosine, l.bm25,
           {lexical_value} AS lexical,
           {semantic_value} AS semantic,
           p.char_count + CASE WHEN btrim(p.heading) <> ''
                               THEN char_length(btrim(p.heading)) + %(heading_overhead)s ELSE 0 END AS evidence_chars
    FROM pool p
    {cosine_join}
    LEFT JOIN lex l USING (chunk_id)
    {lexical_join}
),
scored AS (
    SELECT *, {score} AS score
    FROM ranked
),
kept AS (
    SELECT *, sum(evidence_chars) OVER (ORDER BY score DESC, chunk_id ROWS UNBOUNDED PRECEDING) AS running_chars
    FROM scored
    WHERE score > 0
)
SELECT k.chunk_id, k.score, k.p1, k.p2, k.lexical, k.semantic, k.cosine, k.bm25,
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
_SEMANTIC_VALUE = (
    "greatest(0, least(1, coalesce((p.cosine - cs.median) / nullif(cs.peak - cs.median, 0), 0)))"
)
_NO_SEMANTIC_VALUE = "0::double precision"

# The BM25 index's own scan: it finds the fragments the lexical query matches and scores
# them in one pass, and the best score of the search is what makes L relative to it.
_LEXICAL_CTE = """lex AS (
    SELECT c.chunk_id, pdb.score(c.chunk_id) AS bm25
    FROM chunks c
    WHERE c.chunk_id @@@ {query} {category_and}
),
lex_stats AS (
    SELECT max(bm25) AS peak FROM lex
),"""
_LEXICAL_JOIN = "CROSS JOIN lex_stats ls"
_LEXICAL_VALUE = "coalesce(l.bm25 / nullif(ls.peak, 0), 0)"
# Lexical signal off, or no usable word in the message: nothing matches lexically.
_NO_LEXICAL_CTE = (
    "lex AS (SELECT NULL::bigint AS chunk_id, NULL::double precision AS bm25 WHERE FALSE),"
)
_NO_LEXICAL_JOIN = ""
_NO_LEXICAL_VALUE = "0::double precision"


# Score every fragment for `query` and return the ones that fit the context
# budget, best first (ties by chunk_id, so the order is deterministic).
#
# The query is the user's message. `signals` picks what the score is made of
# (see SearchSignals and the score formula); the signals that are off are not computed,
# in particular the question is not embedded without the semantic signal. A
# fragment with score 0 is not returned. The conditions the message names (see
# ai/conditions.py; each comma-separated expression is recognised on its own)
# decide P1/P2; the lexical signal looks for each expression on its own (see
# lexical_query()); the semantic signal uses the message as typed. `resolved`
# is the message already resolved (the dictionary's conditions completed with
# the ones the AI identified, see condition_ai.resolved_for()); without it the
# message is resolved against the dictionary alone.
# Without any condition in the message the conditions signal is dropped (see
# effective_signals()); the results carry the signals actually used.
#
# category_ids optionally restricts the search to chunks whose category_id is
# one of the given ids (see backend.ai.categories). None means all sources; an
# empty set means zero chunks. The filter is applied before the search
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
    *,
    language: Language | None = None,
) -> list[dict[str, object]]:
    if category_ids is not None and not category_ids:
        return []
    with language_scope(language or current_language()), index_reader() as (connection, metadata):
        return _rank(query, category_ids, max_chars, signals, resolved, connection, metadata)


def _rank(query, category_ids, max_chars, signals, resolved, connection, metadata):
    query = " ".join(query.split())
    if not query:
        return []
    if resolved is None:
        resolved = resolve_query(query)
    if not resolved.segments:  # no word at all, e.g. "?!": nothing to search for
        return []
    signals = effective_signals(signals, resolved)
    condition_names = list(resolved.condition_names) if signals.conditions else []
    lexical = lexical_query(resolved) if signals.lexical else None
    # Every signal that is on has nothing to look for (e.g. only the conditions
    # signal and no condition in the message): no fragment can score.
    if not (condition_names or lexical or signals.semantic):
        return []

    category_where = "WHERE language = %(language)s" + (
        " AND category_id = ANY(%(categories)s)" if category_ids is not None else ""
    )
    category_and = "AND c.language = %(language)s" + (
        " AND c.category_id = ANY(%(categories)s)" if category_ids is not None else ""
    )
    sql = _RANK_SQL.format(
        condition_columns=_CONDITION_COLUMNS if signals.conditions else _NO_CONDITION_COLUMNS,
        cosine_column=_COSINE_COLUMN if signals.semantic else _NO_COSINE_COLUMN,
        category_where=category_where,
        lexical=_LEXICAL_CTE.format(query=lexical[0], category_and=category_and)
        if lexical
        else _NO_LEXICAL_CTE,
        cosine_stats=_COSINE_STATS if signals.semantic else "",
        cosine_join=_COSINE_JOIN if signals.semantic else "",
        lexical_join=_LEXICAL_JOIN if lexical else _NO_LEXICAL_JOIN,
        lexical_value=_LEXICAL_VALUE if lexical else _NO_LEXICAL_VALUE,
        semantic_value=_SEMANTIC_VALUE if signals.semantic else _NO_SEMANTIC_VALUE,
        score=score_sql(),
    )

    parameters: dict[str, object] = {
        "language": current_language(),
        "conditions": condition_names,
        **(lexical[1] if lexical else {}),
        "categories": list(category_ids) if category_ids else None,
        "heading_overhead": len(evidence_heading_prefix()) + len(EVIDENCE_HEADING_SEPARATOR),
        "max_chars": max_chars if max_chars is not None else UNLIMITED_CHARS,
    }
    with connection.cursor(row_factory=namedtuple_row) as cursor:
        if signals.semantic:
            model_name, dimension = metadata.model_name, metadata.model_dimension
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
            vector = np.asarray(
                list(model.query_embed([profile.query_text(query)]))[0], dtype=np.float32
            )
            vector /= np.linalg.norm(vector)
            parameters["vector"] = vector
        rows = cursor.execute(sql, parameters).fetchall()

    display_names = {item.name: item.display_name for item in load_dictionary().conditions}
    return [
        {
            "chunk_id": row.chunk_id,
            "score": float(row.score),
            "condition_in_title": bool(row.p1) if signals.conditions else None,
            "condition_in_text": bool(row.p2) if signals.conditions else None,
            "lexical_score": float(row.lexical) if row.bm25 is not None else None,
            "lexical_bm25": float(row.bm25) if row.bm25 is not None else None,
            "semantic_score": float(row.semantic) if signals.semantic else None,
            "semantic_similarity": float(row.cosine) if signals.semantic else None,
            "found_by_lexical": row.bm25 is not None,
            "business_category": row.business_category,
            "primary_medical_conditions": [
                display_names.get(name, name) for name in row.primary_medical_conditions
            ],
            "secondary_medical_conditions": [
                display_names.get(name, name) for name in row.secondary_medical_conditions
            ],
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
    from backend.config import Settings, configure_settings

    configure_settings(Settings.from_env(dotenv=True))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--language", choices=("ro", "en"), default="ro")
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
    results = rank(args.query, signals=signals, language=validate_language(args.language))
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2, default=lambda value: value.code))
        return
    for position, result in enumerate(results, start=1):
        print(
            f"[{position}] {result['source_relative_path']}:{result['line_start']}-{result['line_end']}"
        )
        if result["heading"]:
            print(f"    {result['heading']}")
        print(
            f"    score={result['score']:.3f} "
            f"P1={int(bool(result['condition_in_title']))} P2={int(bool(result['condition_in_text']))} "
            f"L={result['lexical_score'] or 0.0:.3f} bm25={result['lexical_bm25'] or 0.0:.3f} V={result['semantic_score'] or 0.0:.3f} "
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
