#!/usr/bin/env python3
"""One-off (stage E4 of architecture/plan-conditions-jsonl-si-herbs.md): turns
the approved review list tmp/herbs_candidates.jsonl into data/herbs.jsonl.

Per species: the accepted Latin name (GBIF, with the fixes decided by hand),
the old names as latin_synonyms, the family, the Romanian popular names (the
book, GBIF, names the corpus gives at least twice), the English names (GBIF,
the MatMed index of the corpus). Species that are one and the same are merged.
Also writes tmp/herbs_work/herbs_provenance.jsonl (where every value came from)
for audit_herbs.py."""

from __future__ import annotations

import collections
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_candidates  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.ai.conditions import _fold_word  # noqa: E402
import gbif  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / "tmp" / "herbs_work"
REVIEW = ROOT / "tmp" / "herbs_candidates.jsonl"
TARGET = ROOT / "data" / "herbs.jsonl"
PROVENANCE = WORK / "herbs_provenance.jsonl"
MATMED = ROOT / "data" / "documents" / "Surse necunoscute" / "Dozaj" / "MatMed5 Dozaj tincturi.pdf.md"

FIELDS = ("id", "ro", "ro_regional", "latin", "latin_synonyms", "en", "en_alt", "family")
LATIN = re.compile(r"[A-Z][a-z]+ (x )?[a-z]+(-[a-z]+)?( (subsp|var)\. [a-z]+(-[a-z]+)?)?")

# Misspellings in the review list.
SPELLING = {
    "Fraxinus pallisae": "Fraxinus pallisiae", "Ruscus hipoglossum": "Ruscus hypoglossum",
    "Limonium gmelinii": "Limonium gmelini",
}
# One species under two names (approved): the second name merges into the first.
MERGE = {
    "Cimicifuga europaea": "Actaea europaea", "Anthemis tinctoria": "Cota tinctoria",
    "Ammi visnaga": "Visnaga daucoides", "Pisum sativum": "Lathyrus oleraceus",
    "Lens culinaris": "Vicia lens", "Plantago scabra": "Plantago arenaria",
    "Colchicum fominii": "Colchicum arenarium", "Swertia punctata": "Swertia perennis",
    "Primula officinalis": "Primula veris", "Polygonum bistorta": "Bistorta officinalis",
    "Pinus montana": "Pinus mugo", "Nepeta hederacea": "Glechoma hederacea",
    "Hydrocotyle asiatica": "Centella asiatica", "Eugenia aromatica": "Syzygium aromaticum",
    "Prunus amygdalus": "Prunus dulcis", "Sinapis nigra": "Brassica nigra",
    "Brassica campestris": "Brassica rapa", "Chrysanthemum cinerariaefolium": "Tanacetum cinerariifolium",
    "Curcuma xanthorrhiza": "Curcuma zanthorrhiza", "Plantago psyllium": "Plantago afra",
    "Hydrocharis morsus": "Hydrocharis morsus-ranae", "Lycopersicum esculentum": "Solanum lycopersicum",
}
# Accepted names written by hand: hybrids (GBIF drops the sign), names GBIF files
# wrongly (the citrus hybrids under C. aurantium) or does not know.
FINAL_NAME = {
    "Mentha piperita": "Mentha x piperita", "Fragaria ananassa": "Fragaria x ananassa",
    "Tilia europaea": "Tilia x europaea", "Mentha gracilis": "Mentha x gracilis",
    "Thymus citriodorus": "Thymus x citriodorus", "Populus jackii": "Populus x jackii",
    "Citrus aurantium": "Citrus x aurantium", "Citrus paradisi": "Citrus x paradisi",
    "Citrus sinensis": "Citrus x sinensis",
}
KEEP = {"Pinus nigra subsp. banatica", "Phlomis herba-venti subsp. pungens", "Centaurium littorale subsp. uliginosum",
        "Achillea argentea", "Peucedanum arenarium", "Potentilla ternata"} | set(FINAL_NAME.values())
FAMILY = {"Achillea argentea": "Asteraceae", "Peucedanum arenarium": "Apiaceae", "Potentilla ternata": "Rosaceae",
          "Cinnamomum cassia": "Lauraceae", "Piper methysticum": "Piperaceae", "Prunus dulcis": "Rosaceae",
          "Coleus barbatus": "Lamiaceae"}
# Old names from the sources that are misprints or misattributions, never synonyms.
NOT_SYNONYMS = {"Prunus boldus", "Malva rotundifolia", "Citrus paradisii"}
# Old names GBIF cannot match exactly (it files them under several species) but
# that are true synonyms of the species they were fixed to.
TRUE_SYNONYMS = {"Amygdalus communis", "Allium porrum", "Chenopodium ambrosioides", "Cinnamomum ceylanicum",
                 "Citrus nobilis", "Cochlearia armoracia", "Crataegus oxyacantha", "Epilobium angustifolium",
                 "Oenothera lamarckiana", "Physalis alkekengi", "Polygonum hydropiper", "Pyrus domestica",
                 "Rhus cotinus", "Ribes grossularia", "Ulmus campestris", "Coleus forskohlii"}
# English names where GBIF files the species under another one (the citrus hybrids).
ENGLISH = {
    "Citrus x sinensis": ["Sweet orange", "orange"],
    "Citrus x paradisi": ["Grapefruit"],
    "Citrus x aurantium": ["Bitter orange", "sour orange", "Seville orange"],
}

# Words that show a corpus "name" is a phrase, not a plant name.
NOISE = set("si sau cu din la in pentru ca se care este sunt radacina radacinile frunze frunzele flori florile "
            "seminte ceai tinctura planta plantei parte lingurita lingurite extract pulbere taiata taiate uncie "
            "grame proaspata proaspete zdrobite fiert fierte uscat uscata etc vezi numit numita sub forma parti "
            "the of and root leaf leaves".split())


def plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.replace("ș", "s").replace("ț", "t").replace("ş", "s").replace("ţ", "t"))
    return "".join(c for c in text if not unicodedata.combining(c))


def key(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", plain(text).lower()))


def slug(latin: str) -> str:
    return "-".join(re.findall(r"[a-z]+", latin.lower()))


def clean_ro(name: str) -> str | None:
    name = " ".join(plain(name).replace("*", " ").split()).strip(" -.,;:")
    if not name or not name.isascii() or any(c in name for c in ",()[]{}/"):
        return None
    words = name.lower().replace("-", " ").split()
    if not 1 <= len(words) <= 4 or len(name) < 3:
        return None
    if words[0] in NOISE or words[-1] in NOISE or any(word in NOISE - {"de"} for word in words):
        return None
    return name


# A name folded for comparison: endings of the Romanian articles away, no spaces
# or hyphens (the corpus OCR splits words: "macri sul").
def folded(name: str) -> str:
    joined = key(name).replace(" ", "")
    return _fold_word(_fold_word(joined))


def capitalised(name: str) -> str:
    return name[:1].upper() + name[1:]


# Words kept capitalised in English names when every source writes them in Title Case.
PROPER = set("german roman english hungarian indian american chinese european siberian japanese korean irish "
             "seville spanish greek turkish canadian african virginia california mexican persian egyptian "
             "arabian russian italian french dutch scotch swedish john's st. st jupiter's solomon's "
             "mary's christ's jacob's venus's adam's aaron's judas's job's".split())


def english_names(variants: collections.Counter) -> list[str]:
    # group spellings ("Yarrow" / "yarrow" / "Ox-eye" / "oxeye"), best supported first
    groups: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for name, count in variants.items():
        name = " ".join(plain(name).split())
        if name and name.isascii() and "," not in name and len(name) < 40 and len(name.split()) <= 4:
            groups[key(name).replace(" ", "")][name] += count
    ranked = sorted(groups.values(), key=lambda forms: -sum(forms.values()))
    names = []
    for forms in ranked:
        form = forms.most_common(1)[0][0]
        all_title = all(all(w[:1].isupper() for w in f.split()) for f in forms)
        kept = []
        for word in form.split():
            capital_everywhere = all(any(w == word for w in f.split()) for f in forms if word.lower() in f.lower().split())
            proper = word.lower() in PROPER or (capital_everywhere and not all_title and word[:1].isupper())
            kept.append(word[:1].upper() + word[1:].lower() if proper else word.lower())
        names.append((" ".join(kept), sum(forms.values())))
    return [name for name, _ in names[:1]] + [name for name, count in names[1:] if count >= 2][:3]


def matmed_english() -> dict[str, collections.Counter]:
    # the index of the MatMed tincture list: "Bleeding Heart - Dicentra formosa", "Buckeye, California - Aesculus californica"
    found: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    if not MATMED.exists():
        return found
    text = MATMED.read_text(encoding="utf-8", errors="replace")
    for match in re.finditer(r"([A-Z][A-Za-z' .]+?(?:, [A-Z][a-z]+)?) - ([A-Z][a-z]+ [a-z-]{3,})\b", text):
        english, latin = match.group(1).strip(), match.group(2)
        if "," in english:
            noun, adjective = english.split(", ", 1)
            english = f"{adjective} {noun.lower()}"
        found[latin][english] += 2
    return found


def main() -> None:
    review = [json.loads(line) for line in REVIEW.read_text(encoding="utf-8").splitlines() if line.strip()]
    full = {row["latin"]: row for row in map(json.loads, (WORK / "candidates_full.jsonl").read_text(encoding="utf-8").splitlines())}
    dictionary = [json.loads(line) for line in (WORK / "dictionary_candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    ema = [json.loads(line) for line in (WORK / "ema_species.jsonl").read_text(encoding="utf-8").splitlines()]
    fr_x = [json.loads(line) for line in (WORK / "fr_x.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    corpus_names = json.loads((WORK / "corpus_ro_names.json").read_text(encoding="utf-8"))

    def resolve(name: str) -> str | None:
        name = SPELLING.get(name, name)
        name = build_candidates.NAME_FIXES.get(name, name)
        if name in KEEP or name in build_candidates.KEEP_AS_IS:
            return name
        result = gbif.match(name)
        return gbif.accepted_species(result, min_confidence=80)

    gbif.match_many(sorted({SPELLING.get(row["latin"], row["latin"]) for row in review}))

    species: dict[str, dict] = {}
    order: list[str] = []
    for row in review:
        written = SPELLING.get(row["latin"], row["latin"])
        target = MERGE.get(written, written)
        accepted = target if target in KEEP or target in FINAL_NAME else (resolve(target) or target)
        final = FINAL_NAME.get(accepted, accepted)
        entry = species.get(final)
        if entry is None:
            entry = species[final] = {
                "latin": final, "ro": None, "ro_regional": collections.OrderedDict(), "synonyms": collections.OrderedDict(),
                "sources": [], "names_from": {}, "merged": [], "review_names": [],
            }
            order.append(final)
        if written != final and written not in MERGE:
            entry["synonyms"][written] = "lista revizuita"
        if written in MERGE:
            entry["merged"].append(written)
            entry["synonyms"][written] = "unire de dubluri"
            if row["ro"]:
                entry["ro_regional"].setdefault(row["ro"], "unire de dubluri")
        elif row["ro"] and not entry["ro"]:
            entry["ro"] = row["ro"]
        entry["sources"] += [source for source in row["sources"] if source not in entry["sources"]]
        entry["review_names"].append(row["latin"])
        for name in full.get(row["latin"], {}).get("written", []):
            if name not in NOT_SYNONYMS:
                entry["synonyms"].setdefault(name, "sursa")

    def entry_of(name: str) -> dict | None:
        accepted = resolve(name)
        accepted = FINAL_NAME.get(MERGE.get(accepted, accepted), MERGE.get(accepted, accepted)) if accepted else None
        return species.get(accepted) if accepted else None

    for row in dictionary:
        for name in row["latin"]:
            entry = entry_of(name)
            if entry:
                for popular in [build_candidates.strip_article(row["title"]), *row["popular"]]:
                    entry["ro_regional"].setdefault(popular, "dictionar")
                if name != entry["latin"] and name not in NOT_SYNONYMS:
                    entry["synonyms"].setdefault(name, "dictionar")
    for row in [*ema, *({"species": name} for row in fr_x for name in row["species"])]:
        entry = entry_of(row["species"])
        if entry and row["species"] != entry["latin"]:
            entry["synonyms"].setdefault(row["species"], "EMA / FR X")

    # GBIF: family, Romanian and English vernacular names
    matches = {name: gbif.match(build_candidates.NAME_FIXES.get(name, name.replace(" x ", " "))) for name in order}
    keys = {name: match.get("speciesKey") or match.get("usageKey") for name, match in matches.items()}
    gbif.get_many([(f"species/{k}/vernacularNames", {"limit": 300}) for k in set(keys.values()) if k])
    matmed = matmed_english()

    records, provenance = [], []
    for name in order:
        entry = species[name]
        match = matches[name]
        family = FAMILY.get(name) or match.get("family") or full.get(name, {}).get("family")
        vernacular = gbif.get(f"species/{keys[name]}/vernacularNames", {"limit": 300}).get("results", []) if keys[name] else []
        for item in vernacular:
            if item.get("language") in ("ron", "rum"):
                entry["ro_regional"].setdefault(item["vernacularName"], "GBIF")
        for hint, count in corpus_names.get(name, {}).items():
            if count >= 2:
                entry["ro_regional"].setdefault(hint, "corpus")
        english = collections.Counter(item["vernacularName"] for item in vernacular if item.get("language") == "eng")
        for latin in [name, *entry["synonyms"]]:
            english.update(matmed.get(latin.replace(" x ", " "), {}))
        en_names = ENGLISH.get(name) or english_names(english)

        # the approved Romanian name as reviewed (only the diacritics go); the Latin name when there is none
        ro = capitalised(" ".join(plain(entry["ro"]).split())) if entry["ro"] else name
        regional, regional_from = [], {}
        # compared without articles and word breaks: "sunatoarea" is "sunatoare", "macri sul" is "macrisul"
        seen = {folded(ro), folded(name.split()[0])}
        for raw, origin in entry["ro_regional"].items():
            cleaned = clean_ro(raw)
            if cleaned:
                cleaned = cleaned.lower()
                if folded(cleaned) not in seen:
                    seen.add(folded(cleaned))
                    regional.append(cleaned)
                    regional_from[cleaned] = origin
        # only real names: an exact GBIF match or a synonym fixed by hand, never a misprint of the corpus
        synonyms = [s for s in entry["synonyms"] if LATIN.fullmatch(s) and key(s) != key(name)
                    and (s in TRUE_SYNONYMS or s in entry["merged"] or gbif.match(s).get("matchType") == "EXACT")]
        record = {
            "id": slug(name), "ro": ro, "ro_regional": regional, "latin": name,
            "latin_synonyms": list(dict.fromkeys(synonyms)),
            "en": capitalised(en_names[0]) if en_names else "", "en_alt": en_names[1:] if en_names else [],
            "family": family or "",
        }
        records.append(record)
        provenance.append({"latin": name, "sources": entry["sources"], "merged": entry["merged"],
                           "review_names": entry["review_names"],
                           "ro_regional_from": regional_from, "ro_was_missing": not entry["ro"],
                           "renamed_from": [s for s, why in entry["synonyms"].items() if why == "lista revizuita"]})

    # a Latin synonym may not be another species' name, nor claimed by two species
    latins = {key(r["latin"]) for r in records}
    claimed: dict[str, str] = {}
    for record in records:
        kept = []
        for synonym in record["latin_synonyms"]:
            k = key(synonym)
            if k in latins or k in claimed:
                continue
            claimed[k] = record["latin"]
            kept.append(synonym)
        record["latin_synonyms"] = kept

    records.sort(key=lambda r: (key(r["ro"]), key(r["latin"])))
    with TARGET.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps({field: record[field] for field in FIELDS}, ensure_ascii=False) + "\n")
    with PROVENANCE.open("w", encoding="utf-8", newline="\n") as handle:
        for row in provenance:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    gbif.save()
    print(f"{len(records)} species -> {TARGET}")
    for record in records:
        if not record["family"].endswith("aceae"):
            print(f"family to fix: {record['latin']!r} -> {record['family']!r}")


if __name__ == "__main__":
    main()
