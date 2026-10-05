#!/usr/bin/env python3
"""One-off (stage E3 of architecture/plan-conditions-jsonl-si-herbs.md): joins
the species lists of the sources into one review list.

Sources, all under tmp/herbs_work/:
  fr_x.jsonl                 Farmacopeea Romana X, from knowledge (no document in the corpus)
  dictionary_candidates.jsonl "Dictionarul plantelor de leac" (extract_dictionary_candidates.py)
  corpus_latin.jsonl         Latin names found in the corpus (scan_corpus_names.py)
  corpus_vernacular.jsonl    species the corpus names only by a common name ("spirulina", "chaga")
  ema_species.jsonl          EMA/HMPC herbal monographs (public EMA list)
  ro_literature.jsonl        completions from Romanian medicinal-flora literature (optional)
  exclude.jsonl              species dropped, with the reason (pathogens, no medicinal use)
  review_overrides.jsonl     ro / origin / group decided by hand (optional)
  corpus_ro_names.json       Romanian names the corpus gives next to a Latin one (extract_ro_names.py)

Every name goes through GBIF to its accepted species, so an old name in the
book and the accepted name in EMA become one species. GBIF also gives the
group (plant, fungus, lichen, moss, alga), the WCVP presence in Romania
(native or introduced) and the count of Romanian occurrences, which suggest
the origin. Writes the review list tmp/herbs_candidates.jsonl, sorted by latin,
and everything gathered per species to tmp/herbs_work/candidates_full.jsonl."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gbif  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / "tmp" / "herbs_work"
TARGET = ROOT / "tmp" / "herbs_candidates.jsonl"
# Everything gathered per species (GBIF data, old names, every Romanian name seen), for stage E4.
FULL = WORK / "candidates_full.jsonl"

# Lichen-forming orders (lichens are fungi in GBIF).
LICHEN_ORDERS = {"Lecanorales", "Peltigerales", "Teloschistales", "Caliciales", "Pertusariales",
                 "Umbilicariales", "Lecideales", "Baeomycetales", "Ostropales", "Verrucariales"}
ALGA_PHYLA = {"Rhodophyta", "Chlorophyta", "Charophyta", "Ochrophyta", "Haptophyta", "Myzozoa"}
MOSS_PHYLA = {"Bryophyta", "Marchantiophyta", "Anthocerotophyta"}

# Names GBIF cannot resolve on its own: misprints in the book, and old names it
# files under several accepted species ("Piper methysticum" has three authors)
# -> the accepted species, decided by hand.
NAME_FIXES = {
    "Amygdalus communis": "Prunus dulcis", "Allium porrum": "Allium ampeloprasum",
    "Chenopodium ambrosioides": "Dysphania ambrosioides", "Cinnamomum ceylanicum": "Cinnamomum verum",
    "Cinnamorium camphora": "Cinnamomum camphora", "Citrus nobilis": "Citrus reticulata",
    "Cochlearia armoracia": "Armoracia rusticana", "Crataegus oxyacantha": "Crataegus laevigata",
    "Crysanthemum balsamita": "Tanacetum balsamita", "Crysanthemum vulgare": "Tanacetum vulgare",
    "Curcuma xantorrhiza": "Curcuma zanthorrhiza", "Epilobium angustifolium": "Chamaenerion angustifolium",
    "Erythroxylon coca": "Erythroxylum coca", "Helianthus annus": "Helianthus annuus",
    "Letaria italica": "Setaria italica", "Malva rotundifolia": "Malva neglecta",
    "Metha piperita": "Mentha piperita", "Oenothera lamarckiana": "Oenothera glazioviana",
    "Physalis alkekengi": "Alkekengi officinarum", "Physalis alkenkengil": "Alkekengi officinarum",
    "Piersica vulgaris": "Prunus persica", "Polygonum hydropiper": "Persicaria hydropiper",
    "Prunus boldus": "Peumus boldus", "Pyrus domestica": "Cormus domestica",
    "Rhus cotinus": "Cotinus coggygria", "Ribes grossularia": "Ribes uva-crispa",
    "Trigonella foenum": "Trigonella foenum-graecum", "Ulmus campestris": "Ulmus minor",
    "Vacciniurn vitis-idaea": "Vaccinium vitis-idaea", "Verbascurn thapsiforme": "Verbascum densiflorum",
    "Citrus paradisii": "Citrus paradisi", "Coleus forskohlii": "Coleus barbatus",
}
# Species the corpus scan resolved wrongly (fuzzy matches GBIF got wrong).
CORPUS_FIXES = {"Vaccinium microcarpum": "Vaccinium macrocarpon", "Coleus hadiensis": "Coleus barbatus"}
# Accepted species GBIF still files ambiguously; kept as they are.
# Spirulina is a cyanobacterium (kingdom Bacteria for GBIF), sold and used as an alga.
KEEP_AS_IS = {"Cinnamomum cassia", "Piper methysticum", "Prunus dulcis", "Citrus paradisi", "Coleus barbatus",
              "Arthrospira platensis"}


def read(name: str) -> list[dict]:
    path = WORK / name
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# "Afinul" -> "Afin", "Albastrelele" -> "Albastrele": the book titles carry the
# definite article; the catalogue's ro does not.
def strip_article(title: str) -> str:
    first = re.split(r"\s*/\s*", title)[0].strip()
    words = first.split()
    head = words[0]
    for suffix, replacement in (("ele", "e"), ("ul", ""), ("ua", "a"), ("ia", "ie"), ("a", "a")):
        if head.lower().endswith(suffix) and len(head) > len(suffix) + 2:
            head = head[: len(head) - len(suffix)] + replacement
            break
    return " ".join([head, *words[1:]])


def group_of(result: dict) -> str:
    kingdom, phylum = result.get("kingdom"), result.get("phylum")
    if kingdom == "Fungi":
        return "lichen" if result.get("order") in LICHEN_ORDERS else "ciuperca"
    if kingdom in ("Chromista", "Protozoa", "Bacteria") or phylum in ALGA_PHYLA:
        return "alga"
    if phylum in MOSS_PHYLA:
        return "muschi"
    return "planta"


def main() -> None:
    # The review list is edited by hand once generated; never overwrite those edits.
    if TARGET.exists() and FULL.exists() and TARGET.stat().st_mtime > FULL.stat().st_mtime and "--force" not in sys.argv:
        sys.exit(f"{TARGET} was edited after it was generated; rerun with --force to overwrite it")
    entries: dict[str, dict] = {}

    def add(name: str, source: str, **extra) -> None:
        fixed = NAME_FIXES.get(name) or (name if name in KEEP_AS_IS else None)
        result = gbif.match(fixed or name)
        species = fixed if fixed in KEEP_AS_IS else gbif.accepted_species(result, min_confidence=80) or fixed
        if not species:
            unresolved.append((name, source))
            return
        entry = entries.setdefault(species, {
            "latin": species, "ro": None, "ro_candidates": [], "group": None, "origin": None,
            "sources": [], "written": [], "corpus_documents": [], "drugs": [], "snippet": None,
            "_key": result.get("speciesKey") or result.get("usageKey"), "_match": result,
        })
        if source not in entry["sources"]:
            entry["sources"].append(source)
        if name != species and name not in entry["written"]:
            entry["written"].append(name)
        for key, value in extra.items():
            if isinstance(entry.get(key), list):
                entry[key] += [item for item in value if item not in entry[key]]
            elif value and not entry.get(key):
                entry[key] = value

    unresolved: list[tuple[str, str]] = []
    for row in read("fr_x.jsonl"):
        for name in row["species"]:
            add(name, "FR X", drugs=[row["drug"]])
    for row in read("dictionary_candidates.jsonl"):
        for name in row["latin"]:
            add(name, "dictionar", ro_candidates=[strip_article(row["title"]), *row["popular"]])
    for row in read("corpus_latin.jsonl"):
        documents = sorted(row["documents"])
        add(CORPUS_FIXES.get(row["species"], row["species"]), "corpus", corpus_documents=documents,
            snippet=next(iter(row["documents"].values())),
            written=[name for name in row["written"] if name != row["species"]])
    for row in read("corpus_vernacular.jsonl"):
        add(row["latin"], "corpus", corpus_documents=sorted(row["documents"]),
            snippet=next(iter(row["documents"].values()), None))
    for row in read("ema_species.jsonl"):
        add(row["species"], "EMA", drugs=row["drugs"])
    for row in read("ro_literature.jsonl"):
        add(row["latin"], "literatura RO", ro_candidates=[row["ro"]] if row.get("ro") else [])

    excluded = {row["latin"]: row["reason"] for row in read("exclude.jsonl")}
    overrides = {row["latin"]: row for row in read("review_overrides.jsonl")}
    names_path = WORK / "corpus_ro_names.json"
    corpus_names = json.loads(names_path.read_text(encoding="utf-8")) if names_path.exists() else {}

    keys = sorted({entry["_key"] for entry in entries.values() if entry["_key"]})
    requests = [(f"species/{key}/distributions", {"limit": 300}) for key in keys]
    requests += [(f"species/{key}/vernacularNames", {"limit": 300}) for key in keys]
    requests += [("occurrence/search", {"country": "RO", "taxonKey": key, "limit": 0}) for key in keys]
    gbif.get_many(requests)

    rows = []
    for species, entry in sorted(entries.items()):
        if species in excluded:
            continue
        key = entry.pop("_key")
        result = entry.pop("_match")
        distributions = gbif.get(f"species/{key}/distributions", {"limit": 300}).get("results", []) if key else []
        wcvp = [d for d in distributions if "WCVP" in (d.get("source") or "") and "TDWG:ROM" in (d.get("locationId") or "")]
        vernacular = gbif.get(f"species/{key}/vernacularNames", {"limit": 300}).get("results", []) if key else []
        romanian = [v["vernacularName"] for v in vernacular if v.get("language") in ("ron", "rum", "ro")]
        occurrences = gbif.get("occurrence/search", {"country": "RO", "taxonKey": key, "limit": 0}).get("count", 0) if key else 0
        entry["group"] = group_of(result)
        if wcvp:
            means = (wcvp[0].get("establishmentMeans") or "").upper()
            entry["origin"] = "spontan (introdus)" if means in ("INTRODUCED", "NATURALISED") else "spontan"
        entry["gbif_ro_occurrences"] = occurrences
        entry["wcvp_romania"] = bool(wcvp)
        candidates = list(dict.fromkeys([*entry.pop("ro_candidates"), *romanian, *corpus_names.get(species, {})]))
        entry["ro"] = candidates[0] if candidates else None
        entry["family"] = result.get("family")
        entry.update({k: v for k, v in overrides.get(species, {}).items() if k != "latin"})
        # every other Romanian name seen (book, GBIF, corpus), for the regional names of stage E4
        chosen = (entry["ro"] or "").lower()
        entry["ro_alternatives"] = [name for name in candidates if name.lower() != chosen]
        entry["corpus_document_count"] = len(entry["corpus_documents"])
        rows.append(entry)

    with FULL.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    # The review list (plan 7.6): one species per line, the fields the owner decides on.
    with TARGET.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            sources = [f"corpus:{row['corpus_document_count']}" if source == "corpus" else source
                       for source in row["sources"]]
            handle.write(json.dumps({
                "latin": row["latin"], "ro": row["ro"], "group": row["group"], "origin": row["origin"],
                "sources": sources, "monographs": row["drugs"], "corpus_documents": row["corpus_documents"],
            }, ensure_ascii=False) + "\n")
    print(f"{len(rows)} species ({len(excluded)} excluded) -> {TARGET}")
    for name, source in unresolved:
        print(f"unresolved: {name!r} ({source})")


if __name__ == "__main__":
    main()
