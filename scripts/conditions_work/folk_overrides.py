"""Central owner list for folk synonyms: one folk name per disease.

The chunk agents worked independently and had to leave some folk names unassigned
because a sibling chunk already claimed them ("gusa" for Graves' disease,
"podagra" for gouty arthritis, "jinduitul" for gout). This file is merged last and
decides the owner centrally, so the canonical condition always gets its folk name.

Run:  python folk_overrides.py            # report
      python folk_overrides.py --apply    # insert into data/medical_conditions.txt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent
sys.path.insert(0, str(WORK))
from merge_batches import DICTIONARY, normalize, read_file  # noqa: E402

# folk names to reject: misspellings of a term another condition already owns,
# and descriptive labels rather than names
BLACKLIST = {"ria", "boala secolului", "racul", "prea mult acid la stomac"}

# disease -> folk name (the owner of that folk name in the final file)
OVERRIDES: list[tuple[str, str]] = [
    ("Guta", "jinduitul"),
    ("Gusa", "gusa"),
    ("Boala Graves", "gusa exoftalmica"),
    ("Artrita gutoasa", "podagra"),
    ("Amigdalita", "anghina"),
    ("Icter", "galbeaza"),
    ("Anemie", "sange sarac"),
    ("Alopecie", "chelia"),
    ("Furuncul", "buba coapta"),
    ("Abces", "buba"),
    ("Micoza piciorului", "piciorul atletului"),
    ("Onicomicoza", "ciuperca unghiei"),
    ("Mononucleoza infectioasa", "boala sarutului"),
    ("Varicela", "varsat de vant"),
    ("Pojar", "pojar"),
    ("Rubeola", "pojarul german"),
    ("Tuse convulsiva", "tuse magareasca"),
    ("Rabie", "turbare"),
    ("Antrax", "carbune"),
    ("Febra tifoida", "lingoare"),
    ("Insolatie", "lovitura de soare"),
    ("Hemoragie nazala", "sangerare din nas"),
    ("HemorOizi", "hemoroizi"),
    ("Ascita", "apa in burta"),
    ("Ulcere ale picioarelor", "rana la picior"),
    ("Fractura", "os rupt"),
    ("Entorsa", "intindere"),
    ("Dementa", "ramolire"),
    ("Accident vascular cerebral", "apoplexie"),
    ("Epilepsie", "boala comitiala"),
    ("Astmul bronsic", "naduful"),
    ("Tuberculoza", "ftizie"),
    ("Litiaza biliara", "piatra la fiere"),
    ("Calculi renali", "pietre la rinichi"),
    ("Hipertensiune arteriala", "tensiune mare"),
    ("Hipotensiune arteriala", "tensiune mica"),
    ("Insuficienta cardiaca", "inima slabita"),
    ("Varice", "vene varicoase"),
    ("Tromboza venoasa profunda", "cheag la picior"),
    ("Diabet zaharat", "zahar"),
    ("Hipotiroidism", "tiroida lene"),
    ("Osteoporoza", "oase fragile"),
    ("Artrita reumatoida", "reumatism"),
    ("Lombalgie", "durere de mijloc"),
    ("Insomnie", "lipsa somnului"),
    ("Alcoolism", "betia"),
    ("Candidoza", "bube albe"),
    ("Urticarie", "basicute"),
    ("Acnee", "cosuri"),
    ("Afte bucale", "bube in gura"),
    ("Carie dentara", "carii"),
    ("Cataracta", "piatra neagra"),
    ("Ambliopie", "ochi lenes"),
    ("Surditate", "surzenie"),
    ("Tinitus", "tiuit in urechi"),
    ("Sciatica", "durere de sciatic"),
    ("Sarcina extrauterina", "sarcina pe afara"),
    ("Transpiratie excesiva", "transpiratie"),
    ("Greturi matinale", "greturi"),
    ("Malnutritie", "subnutritie"),
    ("Avitaminoza", "lipsa de vitamine"),
    ("Scabie", "raie"),
    ("Pediculoza", "paduchi"),
    ("Ascaridioza", "limbrici"),
    ("Boli cu transmitere sexuala", "boala rusinoasa"),
    ("Gonoree", "blenoragie"),
    ("Hepatita A", "hepatita molipsitoare"),
    ("Gastrita", "arsura la stomac"),
    ("Reflux gastroesofagian", "reflux"),
    ("Meteorism", "balonare"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    popular: dict[str, str] = {}
    for path in sorted(WORK.glob("POP_[0-9].txt")):
        for line in read_file(path):
            name, _, folk = line.partition("|")
            name, folk = name.strip(), folk.strip()
            if name and folk and normalize(folk) not in BLACKLIST:
                popular.setdefault(normalize(name), folk)

    rows = [[" ".join(field.split()) for field in line.split(",")] for line in read_file(DICTIONARY)]
    index = {normalize(parts[0]): position for position, parts in enumerate(rows)}
    # a folk name may only be used when no other condition already carries it
    existing: dict[str, str] = {}
    for parts in rows:
        for term in parts:
            existing.setdefault(normalize(term), parts[0])

    overrides = 0
    missing = 0
    conflicts = 0
    rejected: list[tuple[str, str, str]] = []

    # 1. central overrides win: they decide the owner of a contested folk name
    for disease, folk in OVERRIDES:
        key = normalize(disease)
        if key not in index:
            missing += 1
            continue
        popular[key] = folk
        overrides += 1

    # 2. attach a folk name only when it is free
    attached: dict[str, str] = {}
    inserted = 0
    for key, folk in popular.items():
        position = index.get(key)
        if position is None:
            conflicts += 1
            continue
        folk_key = normalize(folk)
        owner = existing.get(folk_key) or attached.get(folk_key)
        if owner and normalize(owner) != key:
            rejected.append((rows[position][0], folk, owner))
            continue
        parts = rows[position]
        if folk_key in {normalize(term) for term in parts}:
            continue
        rows[position] = [parts[0], folk, *parts[1:]]
        attached[folk_key] = parts[0]
        inserted += 1

    print(f"folk mappings known       : {len(popular)}")
    print(f"central overrides applied : {overrides} (diseases not found: {missing})")
    print(f"lines now carrying a folk name: {inserted}")
    print(f"folk names already owned elsewhere (skipped): {len(rejected)}")
    for disease, folk, owner in rejected[:20]:
        print(f"  skipped {disease!r}: {folk!r} already means {owner!r}")

    if args.apply:
        rows.sort(key=lambda parts: (normalize(parts[0]), parts[0]))
        DICTIONARY.write_text("\n".join(",".join(parts) for parts in rows) + "\n", encoding="utf-8")
        print(f"written: {DICTIONARY}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
