"""Read-only audit of the PostgreSQL condition catalog: structure, duplicates, anomalies."""

from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.ai.conditions import _normalize, load_dictionary  # noqa: E402
from backend.config import Settings, configure_settings  # noqa: E402

configure_settings(Settings.from_env(dotenv=True))
normalize = _normalize
catalog = load_dictionary()
rows = [(number, list(condition.terms)) for number, condition in enumerate(catalog.conditions, 1)]
widths = collections.Counter(len(parts) for _, parts in rows)
print(f"data rows: {len(rows)}")
print(f"term counts (stored catalog): {dict(sorted(widths.items()))}")


# Audit the effective terms using the runtime normalization rules.
def surviving(parts: list[str]) -> list[str]:
    seen: list[str] = []
    for part in parts:
        key = normalize(part)
        if key and key not in seen:
            seen.append(key)
    return seen


survived = collections.Counter(len(surviving(p)) for _, p in rows)
print(f"normalized unique terms: {dict(sorted(survived.items()))}")

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
