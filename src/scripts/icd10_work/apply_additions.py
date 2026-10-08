"""One-off: step P7 of the ICD-10 plan — insert tmp/icd10_work/add_<L>.jsonl into the dictionary.

Each line of add_<L>.jsonl: {"name": ..., "synonyms": [...], "codes": [...]}.
Before writing anything, every new line is checked against the rules of the
shipped dictionary (ASCII, no comma, at least 6 synonyms, no duplicate term in the
line, canonical name unused, no term already owned by another condition — G6).
Any problem is printed and nothing is written.

The new lines are inserted at their sorted place, key (_normalize(name), name);
every existing line stays byte-for-byte identical.

Run:  python src/scripts/icd10_work/apply_additions.py A [--check]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from backend.ai.conditions import _normalize  # noqa: E402

WORK = ROOT / "tmp" / "icd10_work"
DICTIONARY = ROOT / "medicina-naturista-documente" / "data" / "medical_conditions.jsonl"


def sort_key(name: str) -> tuple[str, str]:
    return (_normalize(name), name)


def problems_of(rows: list[dict], existing: list[dict]) -> list[str]:
    owner: dict[str, str] = {}
    for record in existing:
        for term in [record["name"], *record["synonyms"]]:
            owner.setdefault(_normalize(term), record["name"])
    problems: list[str] = []
    for row in rows:
        name = row["name"]
        terms = [name, *row["synonyms"]]
        if len(row["synonyms"]) < 6:
            problems.append(f"{name}: only {len(row['synonyms'])} synonyms")
        keys = [_normalize(term) for term in terms]
        if len(set(keys)) != len(keys):
            problems.append(f"{name}: duplicate terms in the line {[t for t, k in zip(terms, keys) if keys.count(k) > 1]}")
        for term, key in zip(terms, keys):
            if not term.isascii():
                problems.append(f"{name}: non-ASCII term {term!r}")
            if "," in term or term != " ".join(term.split()) or not term:
                problems.append(f"{name}: malformed term {term!r}")
            if len(term) > 70:
                problems.append(f"{name}: term too long {term!r}")
            if key in owner and owner[key] != name:
                problems.append(f"{name}: term {term!r} already belongs to {owner[key]!r}")
        for key in keys:
            owner.setdefault(key, name)
    return problems


def main() -> int:
    letter = sys.argv[1].upper()
    check_only = "--check" in sys.argv
    source = WORK / f"add_{letter}.jsonl"
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    lines = DICTIONARY.read_text(encoding="utf-8").splitlines()
    existing = [json.loads(line) for line in lines]

    problems = problems_of(rows, existing)
    if problems:
        print("\n".join(problems))
        print(f"{len(problems)} problem(s); nothing written")
        return 1
    if check_only:
        print(f"{letter}: {len(rows)} new conditions pass every check")
        return 0

    keys = [sort_key(record["name"]) for record in existing]
    new_lines = sorted(
        ((sort_key(row["name"]), json.dumps({"name": row["name"], "synonyms": row["synonyms"]}, ensure_ascii=False))
         for row in rows),
    )
    merged: list[str] = []
    position = 0
    for key, line in new_lines:
        while position < len(lines) and keys[position] <= key:
            merged.append(lines[position])
            position += 1
        merged.append(line)
    merged.extend(lines[position:])
    DICTIONARY.write_text("\n".join(merged) + "\n", encoding="utf-8", newline="\n")
    print(f"{letter}: inserted {len(rows)} conditions; dictionary now has {len(merged)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
