"""Read-only audit of data/medical_conditions.jsonl: structure, duplicates, anomalies."""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "data" / "medical_conditions.jsonl"


def plain(value: str) -> str:
    table = str.maketrans("ăâîșțĂÂÎȘȚşţŞŢ", "aaistAAISTstST")
    return value.translate(table)


def normalize(value: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", plain(value).lower(), flags=re.UNICODE))


lines = PATH.read_text(encoding="utf-8").splitlines()
print(f"total lines: {len(lines)}")
print(f"blank lines: {sum(1 for l in lines if not l.strip())}")

widths = collections.Counter()
rows: list[tuple[int, list[str]]] = []
invalid: list[int] = []
for number, line in enumerate(lines, 1):
    if not line.strip():
        continue
    try:
        record = json.loads(line)
        parts = [" ".join(p.split()) for p in [record["name"], *record["synonyms"]]]
    except (ValueError, KeyError, TypeError, AttributeError):
        invalid.append(number)
        continue
    widths[len(parts)] += 1
    rows.append((number, parts))

print(f"invalid lines: {invalid}")
print(f"data rows: {len(rows)}")
print(f"term counts (raw, before dedup): {dict(sorted(widths.items()))}")

# how many fields survive the parser's exact-duplicate removal
def surviving(parts: list[str]) -> list[str]:
    seen: list[str] = []
    for part in parts:
        key = normalize(part)
        if key and key not in seen:
            seen.append(key)
    return seen


survived = collections.Counter(len(surviving(p)) for _, p in rows)
print(f"terms after dedup (parser view): {dict(sorted(survived.items()))}")

# canonical (first) names
canon = [p[0] for _, p in rows]
norm_canon = [normalize(c) for c in canon]
dupe_canon = [k for k, v in collections.Counter(norm_canon).items() if v > 1]
print(f"\nduplicate canonical names (normalized): {len(dupe_canon)}")
for key in sorted(dupe_canon):
    hits = [n for n, c in zip((n for n, _ in rows), norm_canon) if c == key]
    print(f"  {key!r} on lines {hits}")

empty_first = [n for n, p in rows if not normalize(p[0])]
print(f"\nrows with empty canonical name: {empty_first}")

# terms shared between different conditions
owner: dict[str, set[str]] = collections.defaultdict(set)
for _, parts in rows:
    name = normalize(parts[0])
    for part in parts:
        key = normalize(part)
        if key:
            owner[key].add(name)
shared = {k: v for k, v in owner.items() if len(v) > 1}
print(f"terms shared by >1 condition: {len(shared)}")
for key in sorted(shared)[:40]:
    print(f"  {key!r} -> {sorted(shared[key])[:4]}")
if len(shared) > 40:
    print(f"  ... and {len(shared) - 40} more")

# terms that are a strict word-subset of another term (nested ambiguity)
terms = sorted(owner)
padded = {t: f" {t} " for t in terms}
nested: list[tuple[str, str]] = []
termset = set(terms)
for term in terms:
    words = term.split()
    for start in range(len(words)):
        for end in range(start + 1, len(words) + 1):
            sub = " ".join(words[start:end])
            if sub != term and sub in termset:
                nested.append((sub, term))
print(f"\nterms contained in a longer term: {len(nested)}")
for sub, term in nested[:25]:
    print(f"  {sub!r} inside {term!r}")
if len(nested) > 25:
    print(f"  ... and {len(nested) - 25} more")

# non-ascii / diacritics usage in the canonical names
diacritic = [c for c in canon if any(ch in c for ch in "ăâîșțĂÂÎȘȚ")]
print(f"\ncanonical names containing diacritics: {len(diacritic)} -> {diacritic[:15]}")

# canonical names longer than expected / suspicious
print(f"\nlongest canonical names: {sorted(canon, key=len, reverse=True)[:8]}")
print(f"shortest canonical names: {sorted(canon, key=len)[:8]}")
