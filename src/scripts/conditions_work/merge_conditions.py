"""Validate batch files of new conditions against data/medical_conditions.txt.

Usage:  python merge_conditions.py [--apply] [--popular FILE ...] batch1.txt batch2.txt ...

Without --apply: report only (structure errors, duplicates, term collisions).
With --apply: rewrite data/medical_conditions.txt with the surviving new lines
appended, keeping the existing lines byte-for-byte and sorting the additions in
alphabetically after them.

--popular FILE takes a two-column `CanonicalName|folk synonym` file and inserts
the folk synonym into the Romanian block of that condition (and of every line
added in this run), so the popular name becomes a searchable term too.

Dedup rules (the whole file must satisfy them):
  * canonical name (column 1) unique, compared without diacritics/case;
  * every term unique across the whole file (a synonym may belong to one
    condition only), so the dictionary never resolves ambiguously;
  * every line has at least 2 terms (tests/unit/ai/test_conditions.py requires it);
  * no diacritics, no blank fields, no blank lines.
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DICTIONARY = ROOT / "data" / "medical_conditions.txt"
MIN_TERMS = 2
TARGET_COLUMNS = 7

_DIACRITICS = "ăâîșțĂÂÎȘȚşţŞŢ"


def plain(value: str) -> str:
    table = str.maketrans(_DIACRITICS, "aaistAAISTstST")
    return value.translate(table)


def normalize(value: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", plain(value).lower(), flags=re.UNICODE))


def sort_key(line: str) -> tuple[str, str]:
    name = line.split(",")[0]
    return (normalize(name), name)


def read_rows(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def split_terms(line: str) -> list[str]:
    return [" ".join(part.split()) for part in line.split(",")]


# Folk synonyms: `CanonicalName|folk name` -> normalized canonical -> folk term.
def read_popular(paths: list[Path]) -> dict[str, str]:
    popular: dict[str, str] = {}
    for path in paths:
        for line in read_rows(path):
            if "|" not in line:
                continue
            name, _, folk = line.partition("|")
            name, folk = " ".join(name.split()), " ".join(folk.split())
            if name and folk:
                popular.setdefault(normalize(name), folk)
    return popular


# Insert the folk name right after the canonical name of the matching line.
def with_popular(line: str, popular: dict[str, str]) -> str:
    terms = split_terms(line)
    folk = popular.get(normalize(terms[0]))
    if not folk or normalize(folk) in {normalize(term) for term in terms}:
        return line
    return ",".join([terms[0], folk, *terms[1:]])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--popular", nargs="*", type=Path, default=[],
                        help="CanonicalName|folk synonym files")
    args = parser.parse_args()

    popular = read_popular(args.popular)
    base_rows = [with_popular(line, popular) for line in read_rows(DICTIONARY)]
    seen_names: dict[str, str] = {}   # normalized canonical -> original
    seen_terms: dict[str, str] = {}   # normalized term -> owner canonical
    for line in base_rows:
        terms = split_terms(line)
        seen_names[normalize(terms[0])] = terms[0]
        for term in terms:
            seen_terms.setdefault(normalize(term), terms[0])

    accepted: list[str] = []
    problems: list[str] = []
    dropped_names: list[tuple[str, str, str]] = []
    dropped_terms: list[tuple[str, str, str]] = []

    for path in args.files:
        for number, line in enumerate(read_rows(path), 1):
            location = f"{path.name}:{number}"
            terms = split_terms(line)
            if len(terms) < MIN_TERMS:
                problems.append(f"{location} only {len(terms)} term(s): {line[:90]}")
                continue
            if len(terms) < TARGET_COLUMNS:
                problems.append(f"{location} only {len(terms)} columns (<{TARGET_COLUMNS}): {line[:90]}")
            if any(not term for term in terms):
                problems.append(f"{location} has an empty field: {line[:90]}")
                continue
            if any(ch in line for ch in _DIACRITICS):
                problems.append(f"{location} has diacritics: {line[:90]}")
                continue
            if len({normalize(term) for term in terms}) != len(terms):
                problems.append(f"{location} repeats a term inside the line: {line[:90]}")
                continue

            name_key = normalize(terms[0])
            if name_key in seen_names:
                dropped_names.append((location, terms[0], seen_names[name_key]))
                continue

            collisions = [(term, seen_terms[normalize(term)]) for term in terms if normalize(term) in seen_terms]
            if collisions:
                for term, owner in collisions:
                    dropped_terms.append((location, term, owner))
                continue

            for term in terms:
                seen_terms[normalize(term)] = terms[0]
            seen_names[name_key] = terms[0]
            accepted.append(with_popular(",".join(terms), popular))

    print(f"base lines            : {len(base_rows)}")
    print(f"accepted new lines    : {len(accepted)}")
    print(f"dropped (name exists) : {len(dropped_names)}")
    print(f"dropped (term clash)  : {len(dropped_terms)}")
    print(f"structural problems   : {len(problems)}")
    for location, name, owner in dropped_names[:40]:
        print(f"  [name] {location}: {name!r} already as {owner!r}")
    for location, term, owner in dropped_terms[:40]:
        print(f"  [term] {location}: {term!r} already in {owner!r}")
    for problem in problems[:60]:
        print(f"  [struct] {problem}")

    if args.apply:
        accepted.sort(key=sort_key)
        text = "\n".join([*base_rows, *accepted]) + "\n"
        DICTIONARY.write_text(text, encoding="utf-8")
        print(f"\nwritten: {DICTIONARY} ({len(base_rows)} + {len(accepted)} = {len(base_rows) + len(accepted)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
