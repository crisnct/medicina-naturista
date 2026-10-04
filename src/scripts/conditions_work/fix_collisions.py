"""Targeted fixes for terms claimed by two different conditions.

Each fix names the condition that must NOT carry the term: either the term is
dropped from that line, or the two lines are the same disease and are merged.

Run:  python fix_collisions.py [--apply]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent
sys.path.insert(0, str(WORK))
from merge_batches import DICTIONARY, normalize, read_file  # noqa: E402

# (condition keeping the term, condition losing it, term, action)
# action "drop"  -> remove the term from the second condition
# action "merge" -> the second condition is the same disease: fold it into the first
FIXES: list[tuple[str, str, str, str]] = [
    # the human vCJD keeps the folk name; cattle BSE keeps the veterinary ones
    ("Boala Creutzfeldt-Jakob varianta", "Encefalopatie spongiforma bovina", "boala vacii nebune", "drop"),
    ("Boala Creutzfeldt-Jakob varianta", "Encefalopatie spongiforma bovina", "mad cow disease", "drop"),
    # hyposplenism is not asplenia
    ("Hiposplenism", "Asplenie", "asplenie functionala", "drop"),
    ("Hiposplenism", "Asplenie", "functional asplenia", "drop"),
    # gastric MALT lymphoma belongs to the MALT lymphoma line
    ("Limfom MALT", "Limfom gastric", "limfom MALT gastric", "drop"),
    ("Limfom MALT", "Limfom gastric", "MALT lymphoma of the stomach", "drop"),
    ("Limfom MALT", "Limfom gastric", "gastric MALT lymphoma", "drop"),
    # staphylococcal and streptococcal toxic shock are different diseases
    ("Soc toxic stafilococic", "Sindrom de soc toxic streptococic", "Sindrom de soc toxic", "drop"),
    ("Soc toxic stafilococic", "Sindrom de soc toxic streptococic", "soc toxic streptococic", "drop"),
    ("Soc toxic stafilococic", "Sindrom de soc toxic streptococic", "boala prin toxina stafilococica", "drop"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    lines = [[" ".join(field.split()) for field in line.split(",")] for line in read_file(DICTIONARY)]
    index = {normalize(parts[0]): position for position, parts in enumerate(lines)}

    applied = 0
    for keeper, loser, term, action in FIXES:
        keep_key, lose_key, term_key = normalize(keeper), normalize(loser), normalize(term)
        if lose_key not in index:
            print(f"  .. {loser!r} is not a line any more")
            continue
        position = index[lose_key]
        parts = lines[position]
        if action == "drop":
            remaining = [part for part in parts if normalize(part) != term_key]
            if len(remaining) == len(parts):
                print(f"  .. {term!r} not on {loser!r}")
                continue
            if len(remaining) < 2:
                print(f"  !! dropping {term!r} would empty {loser!r}")
                continue
            lines[position] = remaining
            print(f"  drop {term!r} from {parts[0]!r} ({len(parts)} -> {len(remaining)} terms)")
        applied += 1

    print(f"fixes applied: {applied}")
    if args.apply:
        lines.sort(key=lambda parts: (normalize(parts[0]), parts[0]))
        DICTIONARY.write_text("\n".join(",".join(parts) for parts in lines) + "\n", encoding="utf-8")
        print(f"written: {DICTIONARY}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
