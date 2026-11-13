"""Where the question's words and conditions are in the fragments shown to the patient.

Two kinds of highlight, as character ranges over the fragment's displayed text:
  * "searched" - a condition the patient named (the conditions signal), under any of its names;
    found with the same matching that decides P1/P2 (ConditionDictionary.spans);
  * "lexical"  - a word of the question that the lexical signal looks for (not a generic word
    such as "de" or "la"), in any inflected form. Whether a fragment word is the same word is
    decided by the index's own analyzer (stemmer, lowercase, diacritics folded), asked through
    the database, so the highlight agrees with the BM25 match.
"Searched" wins where both apply. Nothing here changes the ranking or the text."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence

from backend.ai.conditions import ResolvedQuery, load_dictionary
from backend.ai.query_terms import GENERIC_QUERY_WORDS, plain
from backend.ai.search import SearchSignals, lexical_terms
from backend.core.contracts import FragmentHighlight
from backend.core.language import current_language

logger = logging.getLogger("naturist.highlights")

_STEMMERS = {"ro": "romanian", "en": "english"}
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
MIN_TERM_CHARS = 3

# The analyzer of the BM25 index (migration 044), applied to the texts it is given: one array
# of tokens per text, one token per word in the order written.
_TOKENS_SQL = """
SELECT pdb.tokenize_simple(t::pdb.simple('stemmer={stemmer}', 'ascii_folding=true'))
FROM unnest(%s::text[]) WITH ORDINALITY AS u(t, i)
ORDER BY i
"""


# The text of a fragment as the panel shows it (and as the ranges refer to it).
def display_text(text: str) -> str:
    return " ".join(text.split())


def _meaningful(word: str) -> bool:
    folded = plain(word)
    return len(folded) >= MIN_TERM_CHARS and folded not in GENERIC_QUERY_WORDS


def _tokens(connection, texts: Sequence[str]) -> list[list[str]]:
    sql = _TOKENS_SQL.format(stemmer=_STEMMERS[current_language()])
    with connection.transaction():  # a savepoint: a failure must not abort the search's transaction
        rows = connection.execute(sql, (list(texts),)).fetchall()
    return [list(row[0]) for row in rows]


def highlights_for(
    connection, texts: Sequence[str], resolved: ResolvedQuery, signals: SearchSignals
) -> list[list[FragmentHighlight]]:
    """One list of non-overlapping, ascending ranges per text (the displayed texts)."""
    words, phrase_names = lexical_terms(resolved) if signals.lexical else ([], set())
    terms = [word for word in words if _meaningful(word)]
    searched_names = resolved.condition_names if signals.conditions else ()
    stems: set[str] = set()
    tokens: list[list[str]] = [[] for _ in texts]
    if terms and texts:
        analyzed = _tokens(connection, [" ".join(terms), *texts])
        stems = set(analyzed[0])
        tokens = analyzed[1:]
    dictionary = load_dictionary() if (searched_names or phrase_names) else None
    result: list[list[FragmentHighlight]] = []
    for text, text_tokens in zip(texts, tokens, strict=True):
        # In order of priority: where two overlap, the first one is kept.
        candidates: list[FragmentHighlight] = []
        if dictionary:
            for start, end in dictionary.spans(text, searched_names):
                candidates.append({"start": start, "end": end, "kind": "searched"})
            for start, end in dictionary.spans(text, phrase_names):
                candidates.append({"start": start, "end": end, "kind": "lexical"})
        if stems:
            matches = list(_WORD.finditer(text))
            if len(matches) == len(text_tokens):
                for match, token in zip(matches, text_tokens, strict=True):
                    if token in stems and _meaningful(match.group()):
                        candidates.append(
                            {"start": match.start(), "end": match.end(), "kind": "lexical"}
                        )
            else:
                # The analyzer and the regex disagree on what a word is (rare characters):
                # no lexical highlight is better than a misplaced one.
                logger.debug(
                    "highlight_tokens_mismatch words=%s tokens=%s", len(matches), len(text_tokens)
                )
        kept: list[FragmentHighlight] = []
        for span in candidates:
            if not any(span["start"] < k["end"] and k["start"] < span["end"] for k in kept):
                kept.append(span)
        result.append(sorted(kept, key=lambda span: span["start"]))
    return result


# Add "highlights" to every evidence item of a finished search; a failure never costs the search.
def apply(evidence, connection) -> None:
    resolved = getattr(evidence, "resolved", None)
    signals = getattr(evidence, "signals", None)
    if resolved is None or signals is None or not evidence:
        return
    try:
        items = list(evidence.values())
        found = highlights_for(
            connection, [display_text(item["text"]) for item in items], resolved, signals
        )
    except Exception:  # noqa: BLE001 - highlighting is decoration
        logger.warning("highlights_failed", exc_info=True)
        return
    for item, spans in zip(items, found, strict=True):
        item["highlights"] = spans
