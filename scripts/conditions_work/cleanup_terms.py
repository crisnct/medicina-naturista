"""Final cleanup: drop the remaining terms that two conditions both claim.

Each line names the condition that LOSES the term; the owner is deduced from the
file, so the fix list stays valid even after the dictionary is rebuilt.

Run:  python cleanup_terms.py [--apply]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent
sys.path.insert(0, str(WORK))
from merge_logic import DICTIONARY, normalize, read_file  # noqa: E402

# (condition that must lose the term, the term)
REMOVE: list[tuple[str, str]] = [
    ("Amiloidoza ATTR", "amiloidoza cardiaca senila"),
    ("Amiloidoza ATTR", "senile cardiac amyloidosis"),
    ("Anemie sideropenica", "anemie sideropenica"),
    ("Anemie sideropenica", "sideropenic anemia"),
    ("Nefrita", "glomerulonefrita"),
    ("Otita", "otita medie"),
    ("Angiodisplazie", "ectazie vasculara intestinala"),
    ("Peritonita tuberculoasa", "enterita tuberculoasa"),
    # a repeated term inside one line is harmless but noisy
    ("Adrenoleucodistrofie", "adrenoleucodistrofie"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    rows = [[" ".join(field.split()) for field in line.split(",")] for line in read_file(DICTIONARY)]
    index = {normalize(parts[0]): position for position, parts in enumerate(rows)}

    # every term must have exactly one owner
    owners: dict[str, list[str]] = {}
    for parts in rows:
        for term in set(parts):
            owners.setdefault(normalize(term), []).append(parts[0])

    applied = 0
    for disease, term in REMOVE:
        key = normalize(disease)
        term_key = normalize(term)
        if key not in index:
            print(f"  .. {disease!r} is not a condition")
            continue
        position = index[key]
        parts = rows[position]
        if term_key not in {normalize(item) for item in parts}:
            continue
        remaining = [item for item in parts if normalize(item) != term_key]
        if len(remaining) < 2:
            print(f"  !! removing {term!r} would empty {disease!r}")
            continue
        rows[position] = remaining
        applied += 1
        # de-duplicate inside every line as well
    cleaned = 0
    for position, parts in enumerate(rows):
        seen, kept = set(), []
        for item in parts:
            key = normalize(item)
            if key and key not in seen:
                seen.add(key)
                kept.append(item)
        if len(kept) != len(parts):
            cleaned += 1
        rows[position] = kept

    # report what is still claimed twice
    owners = {}
    collisions = 0
    for parts in rows:
        for item in parts:
            key = normalize(item)
            if key in owners and owners[key] != parts[0]:
                print(f"  still shared: {item!r} by {parts[0]!r} and {owners[key]!r}")
                collisions += 1
            owners.setdefault(key, parts[0])

    print(f"terms removed        : {applied}")
    print(f"lines de-duplicated  : {cleaned}")
    print(f"remaining collisions : {collisions}")

    if args.apply:
        rows.sort(key=lambda parts: (normalize(parts[0]), parts[0]))
        DICTIONARY.write_text("\n".join(",".join(parts) for parts in rows) + "\n", encoding="utf-8")
        print(f"written: {DICTIONARY}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
