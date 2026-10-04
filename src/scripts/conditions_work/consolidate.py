"""Consolidate genuinely duplicate conditions already present in the dictionary.

A merge directive says: "the condition named KEEP is the same disease as the one
named DROP". The synonyms of DROP are folded into KEEP (dropping the ones already
there), the DROP line disappears, and every merged field survives as a search term.

Run:
  python consolidate.py                 # dry run, prints the plan
  python consolidate.py --apply         # rewrites data/medical_conditions.txt
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DICTIONARY = ROOT / "data" / "medical_conditions.txt"
_TABLE = str.maketrans("ăâîșțşţĂÂÎȘȚŞŢ", "aaiststAAISTST")

# (keep, drop) — only pairs that are the same disease under two names.
MERGES: list[tuple[str, str]] = [
    # --- hard collisions already in the file: two lines claiming the same terms
    ("Adenocarcinom biliar", "Adenocarcinom colangiocelular"),
    ("Adenom hepatic", "Adenom hepatocelular"),
    ("Anemie feripriva", "Anemie sideropenica"),
    # --- same disease, two lines
    ("Abces cutanat", "Abces subcutanat"),
    ("Alergie la acarieni", "Alergie la praf de casa"),
    ("Alunite", "Nevi"),
    ("Angioedem", "Edem angioneurotic"),
    ("Boala Crohn", "Boala inflamatorie intestinala Crohn"),
    ("Boala Huntington", "Coree Huntington"),
    ("Cancer", "Tumora maligna"),
    ("Cardiopatie", "Boala de inima"),
    ("Ciroza hepatica", "Ciroza"),
    ("Dementa", "Dementa senila"),
    ("Diabet zaharat", "Diabet"),
    ("Epilepsie", "Boala comitiala"),
    ("Gripa", "Influenza"),
    ("Hepatita A", "Hepatita infectioasa"),
    ("Hepatita B", "Hepatita virala B"),
    ("Hepatita C", "Hepatita virala C"),
    ("Hernie inghinala", "Hernie abdominala"),
    ("Hipoglicemie", "Glicemie scazuta"),
    ("Hipertensiune arteriala", "Hipertensiune"),
    ("Insuficienta renala", "Boala cronica de rinichi"),
    ("Intoxicatie", "Otravire"),
    ("Leucemie", "Cancer al sangelui"),
    ("Litiaza biliara", "Calculi biliari"),
    ("Metroragie", "Sangerare uterina anormala"),
    ("Otita", "Otita medie"),
    ("Pierderea memoriei", "Tulburari de memorie"),
    ("Sarcina extrauterina", "Sarcina ectopica"),
    ("Sarcom Kaposi", "Sarcomul Kaposi"),
    ("Sindromul oboselii cronice", "Encefalomielita mialgica"),
    ("Tromboflebita", "Tromboza venoasa superficiala"),
    ("Viroza", "Infectie virala"),
]


def normalize(value: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", value.translate(_TABLE).lower(), flags=re.UNICODE))


def sort_key(line: str) -> tuple[str, str]:
    name = line.split(",")[0]
    return (normalize(name), name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    lines = [line for line in DICTIONARY.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_name: dict[str, int] = {}
    fields: list[list[str]] = []
    term_owner: dict[str, str] = {}   # normalized term -> canonical name that carries it
    for index, line in enumerate(lines):
        parts = [" ".join(field.split()) for field in line.split(",")]
        by_name.setdefault(normalize(parts[0]), index)
        for field in parts:
            term_owner.setdefault(normalize(field), parts[0])
        fields.append(parts)

    keep_index: dict[str, int] = {}
    drop_index: dict[str, int] = {}
    for keep, drop in MERGES:
        keep_key, drop_key = normalize(keep), normalize(drop)
        if keep_key not in by_name:
            print(f"  !! keep is not a condition of its own: {keep!r} (but {term_owner.get(keep_key)!r} carries it)")
            continue
        if drop_key in by_name:
            keep_index[keep_key] = by_name[keep_key]
            drop_index[drop_key] = by_name[drop_key]
        elif drop_key in term_owner:
            # already only a synonym of the kept condition: nothing to merge
            print(f"  .. {drop!r} is already a synonym of {term_owner[drop_key]!r}")
        else:
            print(f"  !! {drop!r} is neither a condition nor a synonym")

    merged: list[list[str]] = []
    for index, parts in enumerate(fields):
        if index in drop_index.values():
            continue
        current = list(parts)
        current_key = normalize(current[0])
        targets = [keep for keep, target in keep_index.items() if target == index]
        for target in targets:
            for drop in [d for k, d in MERGES if normalize(k) == target]:
                drop_fields = fields[by_name[normalize(drop)]]
                seen = {normalize(field) for field in current}
                for field in drop_fields:
                    if normalize(field) not in seen:
                        seen.add(normalize(field))
                        current.append(field)
        # the file keeps one canonical name + 3 Romanian + 3 English synonyms
        current = current[:7]
        merged.append(current)

    # a canonical name may never be longer than its own trimmed line
    for parts in merged:
        if len(parts) < 2:
            print(f"  !! line collapsed below 2 terms: {parts}")

    merged.sort(key=lambda parts: (normalize(parts[0]), parts[0]))

    names_seen: dict[str, str] = {}
    terms_seen: dict[str, str] = {}
    problems = 0
    for parts in merged:
        key = normalize(parts[0])
        if key in names_seen:
            print(f"  !! duplicate canonical after merge: {parts[0]!r} / {names_seen[key]!r}")
            problems += 1
        names_seen.setdefault(key, parts[0])
        for field in parts:
            term = normalize(field)
            if term in terms_seen and terms_seen[term] != parts[0]:
                print(f"  !! term {field!r} claimed by {parts[0]!r} and {terms_seen[term]!r}")
                problems += 1
            terms_seen.setdefault(term, parts[0])

    print(f"lines: {len(lines)} -> {len(merged)}  (merged {len(lines) - len(merged)} duplicates)")
    print(f"remaining term/name collisions: {problems}")

    if args.apply:
        DICTIONARY.write_text("\n".join(",".join(parts) for parts in merged) + "\n", encoding="utf-8")
        print(f"written: {DICTIONARY}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
