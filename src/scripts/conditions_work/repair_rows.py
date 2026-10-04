"""Repair rows that lost a field: restore the condition name and pad to 7 columns.

Run:  python repair_rows.py [--apply]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent
sys.path.insert(0, str(WORK))
from merge_logic import DICTIONARY, normalize, read_file  # noqa: E402

# first term -> condition name that must come first
RESTORE_NAME: dict[str, str] = {
    "forma sideropenica de anemie": "Anemie sideropenica",
    "leucodistrofie adrenala": "Adrenoleucodistrofie",
}

# condition -> a genuine extra synonym that no other line uses
EXTRA_SYNONYM: dict[str, str] = {
    "Acondroplazie": "achondroplastic dwarf",
    "Albinism": "albinism of the skin and eyes",
    "Anorexie nervoasa": "anorexia",
    "Astigmatism": "corneal astigmatism",
    "Autism": "childhood autism",
    "Deficit de alfa-1 antitripsina": "alpha-1 proteinase inhibitor deficiency",
    "Encefalopatie spongiforma bovina": "spongiform encephalopathy of cattle",
    "Anemie sideropenica": "anaemia of sideropenic type",
    "Adrenoleucodistrofie": "adrenomyeloneuropathy",
    "Otita": "middle ear infection",
    "Sindrom de soc toxic streptococic": "streptococcal toxic shock-like syndrome",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    rows = [[" ".join(field.split()) for field in line.split(",")] for line in read_file(DICTIONARY)]
    used = {normalize(term) for parts in rows for term in parts}

    renamed = padded = 0
    for parts in rows:
        restore = RESTORE_NAME.get(normalize(parts[0]))
        if restore and normalize(restore) != normalize(parts[0]):
            parts.insert(0, restore)
            renamed += 1
        if len(parts) >= 7:
            continue
        extra = EXTRA_SYNONYM.get(parts[0])
        if not extra:
            print(f"  !! no extra synonym for {parts[0]!r} ({len(parts)} columns)")
            continue
        if normalize(extra) in used:
            print(f"  !! {extra!r} is already used elsewhere")
            continue
        parts.append(extra)
        used.add(normalize(extra))
        padded += 1

    short = [parts[0] for parts in rows if len(parts) < 7]
    print(f"names restored : {renamed}")
    print(f"rows padded    : {padded}")
    print(f"still short    : {short}")

    if args.apply:
        rows.sort(key=lambda parts: (normalize(parts[0]), parts[0]))
        DICTIONARY.write_text("\n".join(",".join(parts) for parts in rows) + "\n", encoding="utf-8")
        print(f"written: {DICTIONARY}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
