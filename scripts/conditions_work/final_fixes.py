"""Last targeted corrections after the bulk pipeline.

  * `Anemie sideropenica` is the same disease as `Anemie feripriva`: fold the two,
    keeping the more common name first (as the user asked for the general name);
  * complete the BSE row, which the collision cleanup left one field short.

Run:  python final_fixes.py [--apply]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent
sys.path.insert(0, str(WORK))
from merge_logic import DICTIONARY, normalize, read_file  # noqa: E402

MERGE_INTO: tuple[str, str] = ("Anemie feripriva", "Anemie sideropenica")
EXTRA: dict[str, str] = {
    "Encefalopatie spongiforma bovina": "mad cow disease",
}

# extra search terms for conditions that exist but are not reachable by a
# common way of naming them (e.g. the generic family name of a rare disease)
TERM_ADD: dict[str, list[str]] = {
    "Porfirie intermitenta acuta": ["porfirie", "acute porphyria"],
    "Artrita idiopatica juvenila": ["boala Still", "Still disease"],
    "Sindrom autoinflamator": ["boala autoinflamatorie", "autoinflammatory disease"],
    "Asfixie perinatala": ["asphyxia at birth"],
    "Sindrom de aspiratie de meconiu": ["meconium aspiration"],
    "Sindrom de abstinenta neonatala": ["neonatal withdrawal", "neonatal abstinence"],
    "Palatoschizis": ["fisura palatina", "cleft palate"],
    "Spina bifida": ["spina bifida", "rachischisis"],
    "Polidactilie": ["polidactilia", "extra fingers"],
    "Sindactilie": ["sindactilia", "webbed fingers"],
    "Sindrom Prader-Willi": ["sindromul Prader-Willi", "Prader-Willi"],
    "Sindrom Angelman": ["sindromul Angelman", "happy puppet syndrome"],
    "Sindrom Williams": ["sindromul Williams", "Williams-Beuren syndrome"],
    "Sindrom CHARGE": ["sindromul CHARGE", "CHARGE association"],
    "Sindrom VACTERL": ["sindromul VACTERL", "VATER association"],
    "Sindrom fragile X": ["sindromul X fragil", "Martin-Bell syndrome"],
    "Comunicare interventriculara": ["defect septal ventricular", "VSD"],
    "Comunicare interatriala": ["defect septal atrial", "ASD"],
    "Persistenta canalului arterial": ["ductus arteriosus permeabil", "patent ductus arteriosus"],
    "Tetralogia Fallot": ["tetralogie Fallot", "Fallot tetralogy"],
    "Coarctatie de aorta": ["coarctatie aortica", "aortic coarctation"],
    "Transpozitie de marile vase": ["transpozitie de vase mari", "great vessel transposition"],
    "Comunicare interventriculara": ["malformatie cardiaca congenitala", "congenital heart defect",
                                     "defect septal ventricular", "VSD"],
    "Febra mediteraneana familiala": ["boala autoinflamatorie", "autoinflammatory disease"],
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    rows = [[" ".join(field.split()) for field in line.split(",")] for line in read_file(DICTIONARY)]
    index = {normalize(parts[0]): position for position, parts in enumerate(rows)}

    merged = 0
    keeper, duplicate = MERGE_INTO
    if normalize(keeper) in index and normalize(duplicate) in index:
        target = index[normalize(keeper)]
        source = index[normalize(duplicate)]
        seen = {normalize(term) for term in rows[target]}
        for term in rows[source]:
            if normalize(term) not in seen:
                seen.add(normalize(term))
                rows[target].append(term)
        rows[source] = []
        merged += 1
        print(f"  merged {duplicate!r} into {keeper!r} ({len(rows[target])} terms)")

    # add the missing common names of conditions that already exist
    used = {normalize(term) for parts in rows for term in parts}
    added_terms = 0
    for disease, terms in TERM_ADD.items():
        key = normalize(disease)
        if key not in index:
            continue
        parts = rows[index[key]]
        have = {normalize(term) for term in parts}
        for term in terms:
            term_key = normalize(term)
            if term_key in have or term_key in used:
                continue
            parts.append(term)
            have.add(term_key)
            used.add(term_key)
            added_terms += 1
    print(f"  extra search terms added: {added_terms}")

    padded = 0
    for parts in rows:
        if not parts:
            continue
        extra = EXTRA.get(parts[0])
        if extra and len(parts) < 7 and normalize(extra) not in {normalize(t) for t in parts}:
            parts.append(extra)
            padded += 1
            print(f"  padded {parts[0]!r} with {extra!r}")

    kept = [parts for parts in rows if parts]
    kept.sort(key=lambda parts: (normalize(parts[0]), parts[0]))

    owners: dict[str, str] = {}
    collisions = 0
    for parts in kept:
        if len(parts) < 7:
            print(f"  !! still short: {parts[0]!r} ({len(parts)})")
        for term in parts:
            key = normalize(term)
            if key in owners and owners[key] != parts[0]:
                print(f"  !! shared term {term!r}: {parts[0]!r} / {owners[key]!r}")
                collisions += 1
            owners.setdefault(key, parts[0])

    print(f"merged: {merged}, padded: {padded}, extra terms: {added_terms}, "
          f"lines: {len(kept)}, collisions: {collisions}")

    if args.apply:
        DICTIONARY.write_text("\n".join(",".join(parts) for parts in kept) + "\n", encoding="utf-8")
        print(f"written: {DICTIONARY}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
