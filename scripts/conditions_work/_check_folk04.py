"""Validator pentru FOLK_04.txt: nume canonice existente, format, duplicate, diacritice."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from pathlib import Path

WORK = Path(__file__).resolve().parent

names = [l.strip() for l in (WORK / "FOLK_names_04.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
known = set(names)
allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -|.'()/")

lines = (WORK / "FOLK_04.txt").read_text(encoding="utf-8").splitlines()

problems: list[str] = []
folk_counter: Counter[str] = Counter()
canon_counter: Counter[str] = Counter()
pairs: set[tuple[str, str]] = set()

for i, line in enumerate(lines, 1):
    if not line.strip():
        problems.append(f"{i}: linie goala")
        continue
    if line != line.strip():
        problems.append(f"{i}: spatii la capete")
    if "|" not in line:
        problems.append(f"{i}: lipseste separatorul |")
        continue
    parts = line.split("|")
    if len(parts) != 2:
        problems.append(f"{i}: mai mult de un | -> {line!r}")
        continue
    canon, folk = parts[0], parts[1]
    if canon not in known:
        problems.append(f"{i}: nume canonic inexistent in lista -> {canon!r}")
    if not folk:
        problems.append(f"{i}: denumire populara goala")
    if "," in folk:
        problems.append(f"{i}: virgula in denumire -> {folk!r}")
    if len(folk) > 40:
        problems.append(f"{i}: denumire prea lunga ({len(folk)}) -> {folk!r}")
    if any(c not in allowed for c in line):
        bad = {c: unicodedata.name(c, "?") for c in line if c not in allowed}
        problems.append(f"{i}: caractere nepermise {bad} -> {line!r}")
    if folk.lower() == canon.lower():
        problems.append(f"{i}: denumirea populara repeta numele canonic -> {line!r}")
    key = (canon, folk.lower())
    if key in pairs:
        problems.append(f"{i}: duplicat exact -> {line!r}")
    pairs.add(key)
    folk_counter[folk.lower()] += 1
    canon_counter[canon] += 1

print(f"linii de date            : {len(lines)}")
print(f"linii valide             : {sum(1 for l in lines if l.strip() and l.count('|') == 1 and not any(c not in allowed for c in l))}")
print(f"boli (canonice) acoperite: {len(canon_counter)}")
print(f"din lista de             : {len(names)} boli")
print(f"termeni populari distincti: {len(folk_counter)}")
print(f"linii goale              : {sum(1 for l in lines if not l.strip())}")

dups = {k: v for k, v in folk_counter.items() if v > 1}
if dups:
    print("\ntermeni populari folositi de mai multe ori (posibile coliziuni):")
    for term, count in sorted(dups.items()):
        owners = [c for c, f in pairs if f == term]
        print(f"  {term!r} x{count}: {', '.join(sorted(set(owners)))}")

print("\nprobleme:", len(problems))
for p in problems:
    print("  " + p)
