import re, unicodedata
from collections import Counter

work = r"D:\Workspace\medicina-naturista\scripts\conditions_work"
names = [l.strip() for l in open(work + r"\FOLK_names_05.txt", encoding="utf-8") if l.strip()]
rows = [l.rstrip("\n") for l in open(work + r"\FOLK_05.txt", encoding="utf-8")]
errors = []
term_owner = {}
canon = set(names)
good = []
for i, line in enumerate(rows, 1):
    if not line.strip():
        errors.append(f"{i}: linie goala")
        continue
    if "|" not in line:
        errors.append(f"{i}: fara |")
        continue
    parts = line.split("|")
    if len(parts) != 2:
        errors.append(f"{i}: prea multe |")
        continue
    c, t = parts[0].strip(), parts[1].strip()
    if c not in canon:
        errors.append(f"{i}: nume canonic inexistent: {c!r}")
    if "," in t:
        errors.append(f"{i}: virgula in termen: {t!r}")
    if len(t) > 40:
        errors.append(f"{i}: termen >40 car: {t!r}")
    if any(ord(ch) > 127 for ch in line):
        errors.append(f"{i}: diacritice/caractere non-ascii: {line!r}")
    if unicodedata.normalize("NFD", t).lower() == unicodedata.normalize("NFD", c).lower():
        errors.append(f"{i}: termen == canonic: {line!r}")
    key = t.lower()
    if key in term_owner and term_owner[key] != c:
        errors.append(f"{i}: termen repetat la alta boala: {t!r} ({term_owner[key]} / {c})")
    term_owner.setdefault(key, c)
    good.append(line)

dups = [k for k, v in Counter([g.split("|")[0] + "|" + g.split("|")[1].lower() for g in good]).items() if v > 1]
print("linii:", len(rows), "valide:", len(good))
print("boli distincte:", len(set(g.split("|")[0] for g in good)))
print("erori:", len(errors))
for e in errors[:40]:
    print("  ", e)
print("duplicate exacte:", dups)
