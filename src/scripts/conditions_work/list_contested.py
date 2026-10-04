"""List every folk name proposed by more than one chunk, with its conditions."""
from __future__ import annotations

import collections
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent
sys.path.insert(0, str(WORK))
from merge_logic import normalize, read_file  # noqa: E402

proposals: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
for path in sorted(WORK.glob("FOLK_[0-9][0-9].txt")):
    for line in read_file(path):
        name, _, folk = line.partition("|")
        if name.strip() and folk.strip():
            proposals[normalize(folk)].append((name.strip(), path.name))

contested = {term: owners for term, owners in proposals.items() if len(owners) > 1}
print(f"contested terms: {len(contested)}\n")
for term, owners in sorted(contested.items()):
    names = sorted({name for name, _ in owners})
    print(f"{term!r}")
    for name in names:
        sources = {source for candidate, source in owners if candidate == name}
        print(f"    {name}   [{', '.join(sorted(sources))}]")
