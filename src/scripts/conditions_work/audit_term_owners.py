"""Read-only: pairs of conditions that share at least one term (possible duplicates)."""
from __future__ import annotations

import collections
import re
from pathlib import Path

PATH = Path(__file__).resolve().parents[3] / "data" / "medical_conditions.txt"
_TABLE = str.maketrans("ăâîșțşţĂÂÎȘȚŞŢ", "aaiststAAISTST")


def normalize(value: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", value.translate(_TABLE).lower(), flags=re.UNICODE))


rows = []
for line in PATH.read_text(encoding="utf-8").splitlines():
    if line.strip():
        rows.append((line.split(",")[0], [" ".join(f.split()) for f in line.split(",")]))

owners: dict[str, set[str]] = collections.defaultdict(set)
for name, fields in rows:
    for field in fields:
        owners[normalize(field)].add(name)

shared_terms = {term: names for term, names in owners.items() if len(names) > 1}
print(f"terms claimed by more than one condition: {len(shared_terms)}\n")

pairs: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
for term, names in shared_terms.items():
    ordered = sorted(names)
    for left in ordered:
        for right in ordered:
            if left < right:
                pairs[(left, right)].append(term)

for (left, right), terms in sorted(pairs.items(), key=lambda item: (-len(item[1]), item[0])):
    print(f"{len(terms):2d} shared: {left!r}  <->  {right!r}")
    for term in sorted(terms):
        print(f"          {term}")

print("\nconditions whose canonical name appears as a synonym of another condition:")
for name, _ in rows:
    key = normalize(name)
    for other, other_fields in rows:
        if other != name and key in {normalize(f) for f in other_fields[1:]}:
            print(f"   {name!r} -> synonym inside {other!r}")
