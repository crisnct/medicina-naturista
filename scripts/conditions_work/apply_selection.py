"""Turn the user's marked selection into the dictionary's folk-name source.

1. keeps the folk names already in the dictionary that came from the earlier POP
   batches (those were approved in the previous session), minus a small blacklist;
2. adds exactly the names the user marked with X in folk_selection.txt;
3. writes them as POP_clean.txt, the single source the pipeline now reads.

Anything not listed in POP_clean.txt stops being attached, which is how the
unselected proposals are removed.

Run:  python apply_selection.py
"""
from __future__ import annotations

import re
import sys
from collections import OrderedDict
from pathlib import Path

WORK = Path(__file__).resolve().parent
sys.path.insert(0, str(WORK))
from merge_logic import DICTIONARY, normalize, read_file  # noqa: E402

SPLIT = re.compile(r"\s*[;,]\s*")
LEADING_NUMBER = re.compile(r"^\d+\s*")
# entries from the earlier POP batches that must not survive
BLACKLIST = {
    "matreata",          # dud/erysipelas label wrongly attached to diarrhoea
    "boala secolului",   # descriptive, not a name
    "ria",               # misspelling of "raie"
}


def main() -> int:
    rows = [[" ".join(f.split()) for f in line.split(",")] for line in read_file(DICTIONARY)]
    # who owns which term in the current dictionary
    owner_of_condition: dict[str, list[str]] = {}
    owner: dict[str, str] = {}
    for parts in rows:
        owner_of_condition[normalize(parts[0])] = parts
        for term in parts:
            owner.setdefault(normalize(term), parts[0])

    # 1. what the earlier POP batches put next to the canonical name
    baseline: "OrderedDict[str, list[str]]" = OrderedDict()
    for path in sorted(WORK.glob("POP_[0-9].txt")):
        for line in read_file(path):
            name, _, folk = line.partition("|")
            name, folk = " ".join(name.split()), " ".join(folk.split())
            key = normalize(name)
            if not name or not folk or normalize(folk) in BLACKLIST:
                continue
            parts = owner_of_condition.get(key)
            if parts is None or normalize(folk) not in {normalize(t) for t in parts}:
                continue          # never made it into the file, so nothing to keep
            bucket = baseline.setdefault(parts[0], [])
            if normalize(folk) not in {normalize(item) for item in bucket}:
                bucket.append(folk)

    # 2. the user's selection
    selected: "OrderedDict[str, list[str]]" = OrderedDict()
    sheet = WORK / "folk_selected.txt"
    for line in sheet.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        body = LEADING_NUMBER.sub("", stripped)
        # an X may sit before the number or right after it
        body = re.sub(r"^X\s*", "", body).strip()
        disease, _, names = body.partition("|")
        disease = LEADING_NUMBER.sub("", disease).strip()
        if not disease or not names:
            continue
        parts = owner_of_condition.get(normalize(disease))
        if parts is None:
            print(f"  !! condition not in the dictionary: {disease!r}")
            continue
        canonical = parts[0]
        bucket = selected.setdefault(canonical, [])
        for value in SPLIT.split(names):
            value = " ".join(value.split()).strip(" .;")
            if not value:
                continue
            holder = owner.get(normalize(value))
            if holder and normalize(holder) != normalize(canonical):
                print(f"  skipped {canonical!r} <- {value!r}: already means {holder!r}")
                continue
            if normalize(value) not in {normalize(item) for item in bucket}:
                bucket.append(value)

    # 3. write the single source file
    merged: "OrderedDict[str, list[str]]" = OrderedDict()
    for disease, values in baseline.items():
        merged[disease] = list(values)
    for disease, values in selected.items():
        bucket = merged.setdefault(disease, [])
        for value in values:
            if normalize(value) not in {normalize(item) for item in bucket}:
                bucket.append(value)

    lines = [f"{disease}|{'|'.join(values)}".replace("|", "|", 1)
             for disease, values in sorted(merged.items(), key=lambda item: normalize(item[0]))]
    # one line per name, as the pipeline expects "Name|folk"
    out_lines: list[str] = []
    for disease, values in sorted(merged.items(), key=lambda item: normalize(item[0])):
        for value in values:
            out_lines.append(f"{disease}|{value}")
    (WORK / "POP_clean.txt").write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    kept_baseline = sum(len(v) for v in baseline.values())
    kept_selected = sum(len(v) for v in selected.values())
    print(f"folk names kept from the earlier batches : {kept_baseline} on {len(baseline)} conditions")
    print(f"folk names from your selection           : {kept_selected} on {len(selected)} conditions")
    print(f"total written to POP_clean.txt           : {len(out_lines)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
