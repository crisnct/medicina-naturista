#!/usr/bin/env python3
"""One-off (stage E3 of architecture/plan-conditions-jsonl-si-herbs.md): finds
the Latin species names in every document of medicina-naturista-documente/data/documents. A "Genus epithet"
pair is kept only when GBIF knows the genus as a plant, fungus or alga genus
AND the whole pair as a species, so Romanian or English sentences that merely
start with a capital ("Planta este") drop out. Writes, per accepted species,
the names as written, the documents and a context snippet, to
tmp/herbs_work/corpus_latin.jsonl."""

from __future__ import annotations

import collections
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gbif  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DOCUMENTS = ROOT / "medicina-naturista-documente" / "data" / "documents"
TARGET = ROOT / "tmp" / "herbs_work" / "corpus_latin.jsonl"

PAIR = re.compile(r"\b([A-Z][a-z]{2,})\s+([a-z]{3,}(?:-[a-z]+)?)\b")
# Abbreviated genus after a full one ("M. officinalis") is not resolved; only full names count.
SNIPPET = 160


def main() -> None:
    pairs: dict[tuple[str, str], dict[str, str]] = collections.defaultdict(dict)  # pair -> {document: snippet}
    for path in sorted(DOCUMENTS.rglob("*.md")):
        relative = path.relative_to(DOCUMENTS).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in PAIR.finditer(text):
            pair = (match.group(1), match.group(2))
            if relative not in pairs[pair]:
                start = max(0, match.start() - SNIPPET // 2)
                pairs[pair][relative] = " ".join(text[start:match.end() + SNIPPET // 2].split())
    genera = sorted({genus for genus, _ in pairs})
    print(f"{len(pairs)} capitalised pairs, {len(genera)} candidate genera")

    genus_results = gbif.match_many(genera, rank="GENUS")
    # A genus name shared with an animal genus ("Urtica", "Thymus", "Melissa")
    # gets no match at all ("Multiple equal matches"); the species check below
    # decides those, since a full species name is not ambiguous.
    known = {
        genus for genus, result in genus_results.items()
        if result.get("matchType") == "EXACT" and result.get("rank") == "GENUS"
        and result.get("kingdom") in gbif.KINGDOMS and result.get("canonicalName") == genus
        or (result.get("note") or "").startswith("Multiple equal matches")
    }
    candidates = sorted(f"{genus} {epithet}" for genus, epithet in pairs if genus in known)
    print(f"{len(known)} genera known to GBIF, {len(candidates)} pairs to check as species")

    species_results = gbif.match_many(candidates)
    found: dict[str, dict] = {}
    for name in candidates:
        result = species_results[name]
        species = gbif.accepted_species(result)
        # A fuzzy match must keep the genus: "Rosa canina" may be misspelt, but
        # "Arnica este" must not become some Arnica species.
        if not species or result.get("genus") != name.split()[0] and result.get("matchType") != "EXACT":
            continue
        if result.get("matchType") == "FUZZY":
            # a misspelling keeps the genus and most of the epithet ("Melissa
            # oficinallis"); a Romanian word after a genus does not ("Astragalus
            # poate" is not Astragalus prattii)
            matched = result.get("canonicalName", "").split()
            if matched[:1] != name.split()[:1] or len(matched) < 2:
                continue
            if difflib.SequenceMatcher(None, name.split()[1], matched[1]).ratio() < 0.8:
                continue
        genus, epithet = name.split()
        record = found.setdefault(species, {
            "species": species, "family": result.get("family"), "kingdom": result.get("kingdom"),
            "written": [], "documents": {},
        })
        record["written"].append(name)
        for document, snippet in pairs[(genus, epithet)].items():
            record["documents"].setdefault(document, snippet)

    with TARGET.open("w", encoding="utf-8", newline="\n") as handle:
        for record in sorted(found.values(), key=lambda item: (-len(item["documents"]), item["species"])):
            record["document_count"] = len(record["documents"])
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"{len(found)} species -> {TARGET}")


if __name__ == "__main__":
    main()
