"""One-off helper: is each query (one per line on stdin) already in the dictionary?

Prints, per query: the condition that has it as a term (exact or with Romanian
endings folded), otherwise the conditions whose terms contain all the query's
key words, otherwise the closest spellings.

Run:  python src/scripts/icd10_work/lookup.py < queries.txt
"""
from __future__ import annotations

import sys
from difflib import get_close_matches
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from match_letter import Dictionary, core, folded  # noqa: E402

from backend.ai.conditions import _normalize  # noqa: E402


def main() -> int:
    dictionary = Dictionary()
    term_core = [(core(term), term, condition.name) for condition in dictionary.conditions for term in condition.terms]
    folded_terms = {" ".join(folded(term)): condition.name for condition in dictionary.conditions for term in condition.terms}
    for raw in sys.stdin.read().splitlines():
        query = raw.strip()
        if not query or query.startswith("#"):
            continue
        hit = dictionary.exact(query)
        if hit:
            print(f"= {query}  ->  {hit[1]}  [{hit[0]}]")
            continue
        key = core(query)
        containing = list(dict.fromkeys(name for words, term, name in term_core if key and key <= words))[:5]
        close = get_close_matches(" ".join(folded(query)), list(folded_terms), n=3, cutoff=0.82)
        close_names = list(dict.fromkeys(folded_terms[term] for term in close))
        if containing or close_names:
            print(f"~ {query}  ->  contine: {' | '.join(containing)}  ||  aproape: {' | '.join(close_names)}")
        else:
            print(f"+ {query}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
