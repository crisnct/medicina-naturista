"""Rank a query with the current dictionary minus one condition (the state before it was added)."""
import sys
from unittest.mock import patch

from backend.ai import conditions, search
from backend.ai.conditions import ConditionDictionary

query, removed, code = sys.argv[1], sys.argv[2], sys.argv[3]
current = conditions.load_dictionary()
without = ConditionDictionary([c for c in current.conditions if c.name != removed])
with patch.object(conditions, "load_dictionary", return_value=without):
    resolved = without.resolve(query)
    results = search.rank(query, signals=search.SearchSignals.from_code(code))
print(f"conditions={resolved.condition_names} segments={[(s.text, s.whole_condition, s.remainder) for s in resolved.segments]}")
print(f"results={len(results)}")
for r in results[:20]:
    print(f"  {r['score']:.3f} P1={int(bool(r['condition_in_title']))} P2={int(bool(r['condition_in_text']))} L={r['lexical_score']} {r['source_relative_path']} [{r['heading']}]")
