#!/usr/bin/env python3
"""One-off (stage E3 of architecture/plan-conditions-jsonl-si-herbs.md): the
Romanian names the corpus gives next to a Latin name, in its two usual forms,
"Abutilon theophrasti Medik. (Pristolnic)" and "Spin (Carduus acanthoides)".
Only Romanian documents are read. Writes latin -> {name: count} to
tmp/herbs_work/corpus_ro_names.json."""

from __future__ import annotations

import collections
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOCUMENTS = ROOT / "medicina-naturista-documente" / "data" / "documents"
CANDIDATES = ROOT / "tmp" / "herbs_candidates.jsonl"
TARGET = ROOT / "tmp" / "herbs_work" / "corpus_ro_names.json"

RO_WORDS = re.compile(r"\b(si|este|sau|pentru|care|din|frunze|radacina|ceai)\b")
EN_WORDS = re.compile(r"\b(the|and|with|for|leaves|root|tea)\b")
WORD = r"[A-ZĂÂÎȘȚŞŢa-zăâîșțşţ][a-zăâîșțşţ-]+"
# Words that open a phrase but are not part of a plant name.
NOT_NAMES = {"Planta", "Plante", "Specia", "Speciile", "Frunzele", "Florile", "Radacina", "Radacinile",
             "Fructele", "Semintele", "Herba", "Tinctura", "Ceaiul", "Infuzia", "Decoctul", "Uleiul",
             "Cum", "Si", "Sau", "De", "La", "In", "Cu", "Din", "Fig", "Familia", "Genul", "Nume", "Denumire"}


AFTER = re.compile(rf"(?:\s+[A-Z][\w.&' -]{{0,25}}?)?\s*\(\s*\*?({WORD}(?:[ -]{WORD}){{0,3}})\s*\*?\)")
BEFORE = re.compile(rf"({WORD}(?:[ -]{WORD}){{0,3}})\s*\*?\s*[({{]\s*\*?\s*$")


def is_romanian(text: str) -> bool:
    sample = text[:200_000].lower()
    return len(RO_WORDS.findall(sample)) > 2 * len(EN_WORDS.findall(sample))


def clean(name: str) -> str | None:
    name = " ".join(name.replace("*", " ").replace("\\", " ").split()).strip(" -,.;:")
    words = name.split()
    while words and words[0] in NOT_NAMES:
        words = words[1:]
    if not words or len(words) > 4 or len(" ".join(words)) < 3:
        return None
    return " ".join(words)


def main() -> None:
    rows = [json.loads(line) for line in CANDIDATES.read_text(encoding="utf-8").splitlines()]
    texts = {}
    found: dict[str, collections.Counter] = {}
    for row in rows:
        counter = collections.Counter()
        for document in row["corpus_documents"]:
            if document not in texts:
                text = (DOCUMENTS / document).read_text(encoding="utf-8", errors="replace")
                texts[document] = text if is_romanian(text) else None
            text = texts[document]
            if not text:
                continue
            for latin in [row["latin"], *row["written"]]:
                genus, _, epithet = latin.partition(" ")
                # find the Latin name first, then look only at a small window around it
                for hit in re.finditer(rf"{re.escape(genus)}\s*\*?\s+{re.escape(epithet)}\b", text):
                    after = text[hit.end():hit.end() + 70]
                    before = text[max(0, hit.start() - 60):hit.start()]
                    # "Latin [Author.] (Name)"
                    match = AFTER.match(after)
                    if match and (name := clean(match.group(1))):
                        counter[name] += 1
                    # "Name (Latin" or "Name *(Latin"
                    match = BEFORE.search(before)
                    if match and (name := clean(match.group(1))):
                        counter[name] += 1
        if counter:
            found[row["latin"]] = dict(counter.most_common())
    TARGET.write_text(json.dumps(found, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(found)} of {len(rows)} species have a Romanian name in the corpus -> {TARGET}")


if __name__ == "__main__":
    main()
