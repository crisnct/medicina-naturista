"""Review the FOLK_*.txt proposals before they reach the dictionary.

Read-only. Reports, for every proposed folk name:
  * whether the canonical condition really exists in the dictionary;
  * whether the folk name is already owned by another condition;
  * weak proposals: sentence-like descriptions instead of a name, very long
    phrases, anything equal to its own canonical name;
  * terms proposed by more than one chunk (the owner must be decided centrally).

Run:  python review_folk.py
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent
sys.path.insert(0, str(WORK))
from merge_logic import DICTIONARY, normalize, read_file  # noqa: E402

# a name, not a description: no sentence glue, no anatomical "la/in/de partea" tail
DESCRIPTION = re.compile(
    r"(?i)\b(partea|partii|zona|zonele|regiunea|mijlocul|lateral|superior|inferior|"
    r"stanga|dreapta|fata|spate|sus|jos|aproape|langa|dintre|peste|sub|intre)\b"
)
MAX_WORDS = 3


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="report only the weak entries")
    args = parser.parse_args()

    rows = [[" ".join(f.split()) for f in line.split(",")] for line in read_file(DICTIONARY)]
    known = {normalize(parts[0]): parts[0] for parts in rows}
    owner: dict[str, str] = {}
    for parts in rows:
        for term in parts:
            owner.setdefault(normalize(term), parts[0])

    proposals: list[tuple[str, str, str]] = []   # (file, canonical, folk)
    for path in sorted(WORK.glob("FOLK_[0-9][0-9].txt")):
        for line in read_file(path):
            name, _, folk = line.partition("|")
            if name.strip() and folk.strip():
                proposals.append((path.name, name.strip(), " ".join(folk.split())))

    by_term: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    for source, name, folk in proposals:
        by_term[normalize(folk)].append((source, name))

    unknown = [p for p in proposals if normalize(p[1]) not in known]
    already = [(s, n, f, owner[normalize(f)]) for s, n, f in proposals
               if normalize(f) in owner and normalize(owner[normalize(f)]) != normalize(n)]
    weak = [(s, n, f) for s, n, f in proposals
            if len(f.split()) > MAX_WORDS
            or DESCRIPTION.search(f)
            or normalize(f) == normalize(n)
            or len(f) > 40]
    contested = {term: owners for term, owners in by_term.items() if len(owners) > 1}

    print(f"proposals                     : {len(proposals)}")
    print(f"conditions with a folk name   : {len({normalize(p[1]) for p in proposals})}")
    print(f"unknown canonical names       : {len(unknown)}")
    print(f"folk names already owned elsewhere: {len(already)}")
    print(f"weak / description-like       : {len(weak)}")
    print(f"terms proposed by >1 chunk    : {len(contested)}\n")

    if unknown:
        print("--- unknown canonical names ---")
        for source, name, folk in unknown[:20]:
            print(f"  {source}: {name!r} (for {folk!r})")
    if already:
        print("\n--- folk name already owned by another condition ---")
        for source, name, folk, holder in already[:30]:
            print(f"  {source}: {name!r} -> {folk!r} (owner: {holder!r})")
    if contested:
        print("\n--- same folk name proposed by several chunks ---")
        for term, owners in sorted(contested.items())[:30]:
            print(f"  {term!r}: {[f'{n} ({s})' for s, n in owners]}")
    if weak:
        print("\n--- weak / description-like proposals ---")
        for source, name, folk in weak[:60]:
            print(f"  {source}: {name!r} -> {folk!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
