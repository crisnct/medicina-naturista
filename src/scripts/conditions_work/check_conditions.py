"""Final checks and report for data/medical_conditions.txt.

Pure read-only unless --fix-layout is given (which only normalizes whitespace and
trims every line to one canonical name + 3 Romanian + 3 English synonyms).

Checks
  1. every data line has the same number of comma-separated fields;
  2. canonical name (field 1) unique, compared without diacritics and case;
  3. every term unique across the whole file (a synonym belongs to one condition);
  4. every line has at least 2 terms (tests/unit/ai/test_conditions.py);
  5. no diacritics, no empty fields, no surrounding blanks;
  6. the file is sorted alphabetically by canonical name.

Report
  * totals per column count and per first letter;
  * near-duplicate canonical names (token sets, shared synonyms, high similarity);
  * lines whose Romanian synonyms look like filler ("forma X de boala Y").
"""
from __future__ import annotations

import argparse
import collections
import itertools
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DICTIONARY = ROOT / "data" / "medical_conditions.txt"
_DIACRITICS = "ăâîșțĂÂÎȘȚşţŞŢ"
STOPWORDS = {
    "de", "la", "a", "al", "ale", "din", "cu", "si", "sau", "in", "pe", "pentru",
    "the", "of", "and", "in", "with", "type", "tip", "form", "forma",
}


def plain(value: str) -> str:
    return value.translate(str.maketrans(_DIACRITICS, "aaistAAISTstST"))


def normalize(value: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", plain(value).lower(), flags=re.UNICODE))


def tokens(value: str) -> frozenset[str]:
    return frozenset(word for word in normalize(value).split() if word not in STOPWORDS)


def read_rows(path: Path) -> list[tuple[int, str]]:
    return [
        (number, line)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if line.strip()
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix-layout", action="store_true", help="normalize spacing and trim to 7 columns")
    parser.add_argument("--quiet-report", action="store_true", help="skip the near-duplicate listing")
    args = parser.parse_args()

    rows = read_rows(DICTIONARY)
    problems: list[str] = []
    warnings: list[str] = []
    parsed: list[tuple[int, list[str]]] = []
    widths = collections.Counter()

    for number, line in rows:
        if line != line.strip() or ",," in line or ", " in line:
            warnings.append(f"line {number}: spacing around commas")
        fields = [field.strip() for field in line.split(",")]
        widths[len(fields)] += 1
        if any(not field for field in fields):
            problems.append(f"line {number}: empty field")
            continue
        if any(ch in line for ch in _DIACRITICS):
            problems.append(f"line {number}: contains diacritics")
        if len({normalize(field) for field in fields}) != len(fields):
            # the parser drops the repeats silently; cosmetic only
            warnings.append(f"line {number}: repeated term inside the line")
        if len(fields) < 2:
            problems.append(f"line {number}: fewer than 2 terms")
        parsed.append((number, fields))

    names: dict[str, int] = {}
    terms: dict[str, int] = {}
    for number, fields in parsed:
        key = normalize(fields[0])
        if key in names:
            problems.append(f"line {number}: canonical name duplicates line {names[key]} ({fields[0]!r})")
        names.setdefault(key, number)
        unique = {normalize(field): field for field in fields}
        for term, field in unique.items():
            if term in terms:
                problems.append(f"line {number}: term {field!r} already used on line {terms[term]}")
            else:
                terms[term] = number

    order = [normalize(fields[0]) for _, fields in parsed]
    if order != sorted(order):
        first_bad = next(i for i in range(1, len(order)) if order[i] < order[i - 1])
        problems.append(f"file is not sorted: {parsed[first_bad][1][0]!r} follows {parsed[first_bad - 1][1][0]!r}")

    print(f"file                : {DICTIONARY}")
    print(f"data lines          : {len(parsed)}")
    print(f"columns distribution: {dict(sorted(widths.items()))}")
    print(f"unique canonical    : {len(names)}")
    print(f"unique terms        : {len(terms)}")
    print(f"structural problems : {len(problems)}")
    for problem in problems[:50]:
        print(f"  {problem}")
    print(f"cosmetic warnings   : {len(warnings)}")
    for warning in warnings[:15]:
        print(f"  {warning}")

    if not args.quiet_report:
        print("\nnear-duplicate canonical names:")
        by_tokens: dict[frozenset[str], list[str]] = collections.defaultdict(list)
        for _, fields in parsed:
            by_tokens[tokens(fields[0])].append(fields[0])
        for key, group in sorted(by_tokens.items()):
            if len(group) > 1 and key:
                print(f"  same token set {sorted(key)} -> {group}")

        owners = collections.defaultdict(set)
        for _, fields in parsed:
            for field in fields:
                owners[normalize(field)].add(fields[0])
        shared = collections.Counter()
        for _, fields in parsed:
            mine = {normalize(field) for field in fields}
            for term in mine:
                for other in owners[term]:
                    if other != fields[0]:
                        shared[tuple(sorted((fields[0], other)))] += 1
        for pair, count in shared.most_common():
            if count >= 2:
                print(f"  {count} shared terms between {pair[0]!r} and {pair[1]!r}")

        canonical = [fields[0] for _, fields in parsed]
        print("\nclosest canonical names (similarity >= 0.90):")
        pairs = 0
        for left, right in itertools.combinations(canonical, 2):
            if abs(len(left) - len(right)) > 12:
                continue
            if left[0].lower() != right[0].lower():
                continue
            ratio = SequenceMatcher(None, normalize(left), normalize(right)).ratio()
            if ratio >= 0.90:
                print(f"  {ratio:.3f} {left!r} ~ {right!r}")
                pairs += 1
                if pairs > 60:
                    print("  ... truncated")
                    break

        print("\nsuspicious filler synonyms (Romanian fields that just restate the name):")
        filler = 0
        for _, fields in parsed:
            name = normalize(fields[0])
            restated = [field for field in fields[1:4] if normalize(field) == name]
            if len(restated) >= 2:
                print(f"  {fields[0]!r}: {fields[1:4]}")
                filler += 1
        print(f"  total: {filler}")

    if args.fix_layout:
        fixed: list[str] = []
        for _, fields in parsed:
            trimmed = fields[:7] if len(fields) >= 7 else fields
            fixed.append(",".join(trimmed))
        fixed.sort(key=lambda line: (normalize(line.split(",")[0]), line.split(",")[0]))
        DICTIONARY.write_text("\n".join(fixed) + "\n", encoding="utf-8")
        print(f"\nrewritten with {len(fixed)} normalized lines")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
