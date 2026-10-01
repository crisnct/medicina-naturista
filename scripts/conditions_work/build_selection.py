"""Build the preview of the folk names the user marked with X.

Reads scripts/conditions_work/folk_selection.txt, where the user put X in front of
the lines to keep and may have appended extra names after a comma. Several names on
one line are split into one name per line, because the dictionary stores one term
per comma-separated field.

Writes:
    folk_selected.txt  - what will be added (one name per line, numbered)
    folk_rejected.txt  - the proposed names that were NOT marked
"""
from __future__ import annotations

import re
import sys
from collections import OrderedDict
from pathlib import Path

WORK = Path(__file__).resolve().parent
SHEET = WORK / "folk_selection.txt"
SPLIT = re.compile(r"\s*[;,]\s*")
NUMBER = re.compile(r"^\d+\s*")


def clean(value: str) -> str:
    return " ".join(value.split()).strip(" .;")


def main() -> int:
    picked: "OrderedDict[str, list[str]]" = OrderedDict()
    rejected: "OrderedDict[str, list[str]]" = OrderedDict()
    for line in SHEET.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        keep = stripped[:1].upper() == "X"
        body = stripped[1:].strip() if keep else stripped
        disease, _, names = body.partition("|")
        disease = NUMBER.sub("", disease).strip()
        if not disease or not names:
            continue
        values = [clean(name) for name in SPLIT.split(names) if clean(name)]
        target = picked if keep else rejected
        bucket = target.setdefault(disease, [])
        for value in values:
            if value not in bucket:
                bucket.append(value)

    selected_lines: list[str] = []
    counter = 0
    for disease in sorted(picked, key=str.lower):
        for folk in picked[disease]:
            counter += 1
            selected_lines.append(f"{counter:4} {disease} | {folk}")

    rejected_lines = [f"{disease} | {'; '.join(values)}"
                      for disease, values in sorted(rejected.items(), key=lambda item: item[0].lower())]

    header = [
        "# Denumirile populare pe care LE-AI SELECTAT (X). Vor fi adaugate in dictionar.",
        "# Un rand = o denumire. Numarul este doar pentru referinta.",
        "#",
    ]
    (WORK / "folk_selected.txt").write_text("\n".join(header + selected_lines) + "\n", encoding="utf-8")
    (WORK / "folk_rejected.txt").write_text("\n".join(rejected_lines) + "\n", encoding="utf-8")

    print(f"boli selectate        : {len(picked)}")
    print(f"denumiri selectate    : {sum(len(v) for v in picked.values())}")
    print(f"boli cu propuneri respinse: {len(rejected)}")
    print(f"denumiri respinse     : {sum(len(v) for v in rejected.values())}")
    print()
    print(f"scris: {WORK / 'folk_selected.txt'}")
    print(f"scris: {WORK / 'folk_rejected.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
