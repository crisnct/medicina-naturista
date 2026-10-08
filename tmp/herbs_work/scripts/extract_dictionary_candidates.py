#!/usr/bin/env python3
"""One-off (stage E3 of architecture/plan-conditions-jsonl-si-herbs.md): reads
"Dictionarul plantelor de leac" from the corpus and writes, for every "### "
entry, its title, the Latin names and the popular names the book gives, to
tmp/herbs_work/dictionary_candidates.jsonl."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "medicina-naturista-documente" / "data" / "documents" / "Surse sigure" / "Dictionarul plantelor de leac" / "Dictionarul-Plantelor-de-Leac.pdf.md"
TARGET = ROOT / "tmp" / "herbs_work" / "dictionary_candidates.jsonl"

FIELD = re.compile(r"^Denumir(?:e|ea|i)\s+(stiintific[ae]|popular[ae])\s*[:.]\s*(.*)$", re.IGNORECASE)
# A Latin species name: Genus epithet, optionally "subsp./var. x"; "Genus sp." is kept as a genus.
LATIN = re.compile(r"\b([A-Z][a-z]+(?: x)? (?:[a-z]+(?:-[a-z]+)?|sp\.)(?: (?:subsp|ssp|var)\. [a-z]+(?:-[a-z]+)?)?)")
# Lines that end a field's continuation.
STOP = re.compile(r"^(Denumir|Prezentare|Substante|Intrebuintari|Mod de|Recoltare|#|\d+ DICTIONARUL)", re.IGNORECASE)


def entries(text: str):
    title, lines = None, []
    for line in text.splitlines():
        if line.startswith("### "):
            if title:
                yield title, lines
            title, lines = line[4:].strip(), []
        elif line.startswith("## "):
            if title:
                yield title, lines
            title, lines = None, []
        elif title:
            lines.append(line)
    if title:
        yield title, lines


def fields(lines: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    current = None
    for line in lines:
        match = FIELD.match(line.strip())
        if match:
            current = "latin" if match.group(1).lower().startswith("stiint") else "popular"
            # "Denumire populara: Marrubium vulgare" — a mislabelled scientific name
            if current == "popular" and "latin" not in found and LATIN.fullmatch(match.group(2).strip().rstrip(".")):
                current = "latin"
            found[current] = match.group(2).strip()
        elif current and line.strip() and not STOP.match(line.strip()):
            found[current] += " " + line.strip()
        else:
            current = None
    return found


def popular_names(value: str) -> list[str]:
    value = re.sub(r"\s+", " ", value).strip().rstrip(".")
    value = re.split(r" [–-] ", value)[0]  # "angelina, ... – aceleasi ca si pentru ..."
    names = []
    for part in re.split(r"[,;]", value):
        part = part.strip().strip(".").strip()
        if part and len(part) < 60:
            names.append(part)
    return names


def main() -> None:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for title, lines in entries(SOURCE.read_text(encoding="utf-8")):
        found = fields(lines)
        latin = re.sub(r"\s+", " ", found.get("latin", ""))
        if not latin:
            # no field, but the presentation names the species: "Ghintura albastra (Gentiana asclepiadea)"
            first = " ".join(lines[:3])
            latin = " ".join(re.findall(r"\(([A-Z][a-z]+ [a-z-]+)\)", first))
        records.append({
            "title": title,
            "latin_raw": latin,
            "latin": list(dict.fromkeys(m.replace(" ssp.", " subsp.") for m in LATIN.findall(latin))),
            "popular": popular_names(found.get("popular", "")),
        })
    with TARGET.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    without = [r["title"] for r in records if not r["latin"]]
    print(f"{len(records)} entries, {len(without)} without a Latin name -> {TARGET}")
    print("without Latin name:", without)


if __name__ == "__main__":
    main()
