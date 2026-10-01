"""Build the review sheet the user marks with X.

One line per condition, all its added folk names on that line:

    1 Abces cutanat | buba
    2 Alcoolism | betia; betie

The user puts X at the start of the lines to KEEP (and may delete names he does
not want from the line); everything without X is removed from the dictionary.

Writes: folk_to_review.txt   (fresh sheet, with a short usage header)
"""
from __future__ import annotations

import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent
sys.path.insert(0, str(WORK))
from merge_logic import DICTIONARY, normalize, read_file  # noqa: E402
from folk_overrides import BLACKLIST, OVERRIDES  # noqa: E402

HEADER = """# Puneti un X la inceputul randului pentru denumirile populare pe care le pastrati.
# Puteti sterge din rand denumirile care nu va plac (ramanand X pe rand).
# Randurile fara X pierd toate denumirile populare de pe ele.
#
# Randurile marcate cu [!] sunt cele considerate slabe (ecou al numelui bolii sau descriere).
# Randurile marcate cu [*] au mai multe denumiri, dintre care unele par slabe.
#
# Format:  X  <numar> <NumeBoala> | denumire populara; alta denumire
#
"""


def looks_weak(disease: str, folk: str) -> bool:
    stop = {"de", "la", "din", "cu", "pe", "in", "si", "sau", "a", "al", "ale", "un", "o"}
    disease_words = {w for w in normalize(disease).split() if w not in stop}
    folk_words = {w for w in normalize(folk).split() if w not in stop}
    if not folk_words:
        return True
    if folk_words <= disease_words:
        return True
    if len(folk.split()) >= 5:
        return True
    if len(folk_words) == 1 and folk_words & disease_words:
        return True
    return False


def main() -> int:
    proposals: dict[str, list[str]] = {}
    for pattern in ("POP_[0-9].txt", "FOLK_[0-9][0-9].txt"):
        for path in sorted(WORK.glob(pattern)):
            for line in read_file(path):
                name, _, folk = line.partition("|")
                name, folk = " ".join(name.split()), " ".join(folk.split())
                if not name or not folk or normalize(folk) in BLACKLIST:
                    continue
                bucket = proposals.setdefault(name, [])
                if normalize(folk) not in {normalize(item) for item in bucket}:
                    bucket.append(folk)
    for disease, folk in OVERRIDES:
        bucket = proposals.setdefault(disease, [])
        if normalize(folk) not in {normalize(item) for item in bucket}:
            bucket.append(folk)

    owner: dict[str, str] = {}
    for line in read_file(DICTIONARY):
        parts = [" ".join(f.split()) for f in line.split(",")]
        for term in parts:
            owner.setdefault(normalize(term), parts[0])

    rows: list[tuple[str, list[str], str]] = []
    for disease, values in proposals.items():
        keep = [folk for folk in values if owner.get(normalize(folk)) == disease]
        if not keep:
            continue
        weak_count = sum(1 for folk in keep if looks_weak(disease, folk))
        mark = "[!]" if weak_count == len(keep) else ("[*]" if weak_count else "   ")
        rows.append((disease, keep, mark))
    # the doubtful ones first, then alphabetically, so they are easy to find
    rows.sort(key=lambda item: (item[2] == "   ", normalize(item[0])))

    lines = [HEADER.rstrip("\n")]
    for number, (disease, values, mark) in enumerate(rows, 1):
        lines.append(f"   {number:4} {mark} {disease} | {'; '.join(values)}")

    out = WORK / "folk_to_review.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    weak_rows = sum(1 for _, _, mark in rows if mark == "[!]")
    mixed = sum(1 for _, _, mark in rows if mark == "[*]")
    print(f"conditions listed        : {len(rows)}")
    print(f"folk names listed        : {sum(len(values) for _, values, _ in rows)}")
    print(f"lines fully doubtful [!] : {weak_rows}")
    print(f"lines partly doubtful [*]: {mixed}")
    print(f"written                  : {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
