"""Read-only: existing canonical names that are word-subsets of another canonical name."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.ai.conditions import _normalize  # noqa: E402

PATH = Path(__file__).resolve().parents[2] / "data" / "medical_conditions.txt"
rows = []
for line in PATH.read_text(encoding="utf-8").splitlines():
    if not line.strip() or line.strip().startswith("#"):
        continue
    rows.append([p.strip() for p in line.split(",")])

canon = [r[0] for r in rows]
norm = {_normalize(c): c for c in canon}
keys = sorted(norm)
key_set = set(keys)

print("A) canonical name contained in another canonical name (word-subset):")
count = 0
for key in keys:
    words = key.split()
    for start in range(len(words)):
        for end in range(start + 1, len(words) + 1):
            sub = " ".join(words[start:end])
            if sub != key and sub in key_set:
                print(f"   {norm[sub]!r}  <inside>  {norm[key]!r}")
                count += 1
print(f"   total pairs: {count}")

print()
print("B) canonical names identical after dropping leading 'alergie la' / plural noise:")
stripped: dict[str, list[str]] = {}
for c in canon:
    base = _normalize(c)
    base = re.sub(r"^(alergie la|alergie|abces|adenom|adenocarcinom)\s+", "", base)
    base = re.sub(r"s$", "", base)
    stripped.setdefault(base, []).append(c)
for base, names in sorted(stripped.items()):
    if len(names) > 1:
        print(f"   {base!r} <- {names}")

print()
print("C) first-column values not starting with an uppercase letter:", [c for c in canon if not c[:1].isupper()])
print("D) first-column values with trailing/leading issues:", [c for c in canon if c != c.strip() or "  " in c])
print(f"E) canonical names containing a comma-safe Latin-1 char: "
      f"{[c for c in canon if any(ord(ch) > 127 for ch in c)]}")
