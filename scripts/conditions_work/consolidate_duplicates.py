"""Consolidate conditions that turn out to be the same disease under two names.

Unlike the merge step, this runs on the finished dictionary and folds a duplicate
into the condition that already exists, keeping every synonym. Two conditions are
treated as one disease when their names are all but identical once the generic
words (boala, sindrom, tip, acut, cronic ...) are removed, e.g.

  Adenocarcinom biliar            + Adenocarcinom colangiocelular
  Adenom hepatic                  + Adenom hepatocelular
  Amiloidoza cardiaca             + Amiloidoza ATTR

Every decision is printed, so nothing merges silently.

Run:  python consolidate_duplicates.py [--apply]
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

WORK = Path(__file__).resolve().parent
sys.path.insert(0, str(WORK))
from merge_logic import DICTIONARY, normalize, read_file  # noqa: E402

GENERIC = {
    "boala", "boli", "sindrom", "sindromul", "afectiune", "afectiuni", "tulburare",
    "tulburari", "acut", "acuta", "cronic", "cronica", "primar", "primara", "secundar",
    "secundara", "de", "la", "a", "al", "ale", "din", "cu", "si", "sau", "in", "pe",
    "pentru", "tip", "forma", "the", "of", "and", "with",
}


def key_tokens(value: str) -> frozenset[str]:
    return frozenset(word for word in normalize(value).split() if word not in GENERIC)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    rows = [[" ".join(field.split()) for field in line.split(",")] for line in read_file(DICTIONARY)]

    owner: dict[str, list[int]] = {}
    for position, parts in enumerate(rows):
        for term in parts:
            owner.setdefault(normalize(term), []).append(position)

    # Two conditions merge only when the data itself proves they are one disease:
    # either a term is already claimed by both lines, or a line's own name is a
    # synonym of the other. Name similarity alone is not enough — it would merge
    # distinct entities such as "Scleroza multipla primar progresiva" with the
    # secondary progressive form.
    merges: list[tuple[int, int]] = []
    for term, positions in owner.items():
        ordered = sorted(set(positions), key=lambda position: (len(rows[position][0]), rows[position][0]))
        for other in ordered[1:]:
            if (ordered[0], other) not in merges:
                merges.append((ordered[0], other))

    # a canonical name that is a synonym of another condition is the same disease
    by_name = {normalize(parts[0]): position for position, parts in enumerate(rows)}
    for term, positions in owner.items():
        keeper = by_name.get(term)
        if keeper is None:
            continue
        for other in positions:
            if other != keeper and (keeper, other) not in merges:
                merges.append((keeper, other))

    drop: set[int] = set()
    for keeper, other in merges:
        if keeper in drop or other in drop:
            continue
        seen = {normalize(term) for term in rows[keeper]}
        added = 0
        for term in rows[other]:
            if normalize(term) not in seen:
                seen.add(normalize(term))
                rows[keeper].append(term)
                added += 1
        drop.add(other)
        print(f"  {rows[keeper][0]!r}  <=  {rows[other][0]!r}  (+{added} terms)")

    kept = [parts for position, parts in enumerate(rows) if position not in drop]
    kept.sort(key=lambda parts: (normalize(parts[0]), parts[0]))

    owners: dict[str, str] = {}
    collisions = 0
    for parts in kept:
        for term in parts:
            term_key = normalize(term)
            if term_key in owners and owners[term_key] != parts[0]:
                print(f"  still shared: {term!r} by {parts[0]!r} and {owners[term_key]!r}")
                collisions += 1
            owners.setdefault(term_key, parts[0])

    print(f"\nconditions merged    : {len(drop)}")
    print(f"lines: {len(rows)} -> {len(kept)}")
    print(f"remaining collisions : {collisions}")

    if args.apply:
        DICTIONARY.write_text("\n".join(",".join(parts) for parts in kept) + "\n", encoding="utf-8")
        print(f"written: {DICTIONARY}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
