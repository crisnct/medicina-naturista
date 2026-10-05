"""Rank one query with the current JSONL dictionary and with the .txt from git HEAD."""
import sys
from unittest.mock import patch

from backend.ai import conditions, search
from backend.ai.conditions import Condition, ConditionDictionary, _normalize


def parse_txt(text):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        terms, seen = [], set()
        for part in line.split(","):
            part = " ".join(part.split())
            key = _normalize(part)
            if key and key not in seen:
                seen.add(key)
                terms.append(part)
        out.append(Condition(terms[0], tuple(terms)))
    return out


query = sys.argv[1]
old = ConditionDictionary(parse_txt(open("tmp/medical_conditions-HEAD.txt", encoding="utf-8").read()))
new = conditions.load_dictionary()
for label, dictionary in (("HEAD .txt", old), ("JSONL", new)):
    with patch.object(conditions, "load_dictionary", return_value=dictionary):
        resolved = dictionary.resolve(query)
        results = search.rank(query, signals=search.SearchSignals.from_code(sys.argv[2] if len(sys.argv) > 2 else "ABC"))
    print(f"== {label}: conditions={resolved.condition_names} segments={[(s.text, s.whole_condition, s.remainder) for s in resolved.segments]}")
    print(f"   terms={[c.terms for c in resolved.conditions]}")
    print(f"   results={len(results)}")
    for r in results[:20]:
        print(f"   {r['score']:.3f} P1={int(bool(r['condition_in_title']))} P2={int(bool(r['condition_in_text']))} L={r['lexical_score']} {r['source_relative_path']} [{r['heading']}]")
