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
    # --- owner decisions for folk names proposed by several chunks at once
    #     (matching the condition the folk name really denotes)
    ("Malarie", "friguri"),
    ("Febra", "febra mare"),
    ("Hipertiroidism", "gusa tiroidiana"),
    ("Hipotiroidism", "tiroida lene"),
    ("Difterie", "gusa copilului"),
    ("Boala Graves", "gusa exoftalmica"),
    ("Calculi renali", "piatra la rinichi"),
    ("Rinita", "guturai"),
    ("Gripa", "gripa"),
    ("Hepatita", "hepatita molipsitoare"),
    ("Dizenterie", "dizenterie"),
    ("Diaree", "diaree"),
    ("Colita hemoragica", "diaree cu sange"),
    ("Alcoolism", "betie"),
    ("Narcolepsie", "boala somnului"),
    ("Encefalita letargica", "encefalita somnului"),
    ("Impetigo", "bube"),
    ("Eczema", "bube de piele"),
    ("Furuncul", "buba rea"),
    ("Ectima", "rana murdara"),
    ("Abces", "buboi"),
    ("Coptura", "buba de la fund"),
    ("Mononucleoza infectioasa", "boala sarutului"),
    ("Scabie", "raie"),
    ("Demodicoza", "acarieni la fata"),
    ("Strabism", "ochi incrucisati"),
    ("Esotropie", "ochi care se abat spre nas"),
    ("Cardiomegalie", "inima marita"),
    ("Cord pulmonar", "inima obosita de plamani"),
    # --- second round: owners for the terms several FOLK chunks proposed at once
    ("Matreata", "matreata"),
    ("Menoragie", "sangerare menstruala"),
    ("Gonoree", "boala rusinoasa"),
    ("Herpes labial", "buba rece"),
    ("Sifilis primar", "buba tare"),
    ("Furuncul", "buba rea"),
    ("Flebotromboza", "cheag la picior"),
    ("Tromboza venoasa profunda", "cheag la vena"),
    ("Chist renal simplu", "chist la rinichi"),
    ("Chist renal complicat", "chist cu apa la rinichi"),
    ("Cancer testicular", "cancer la testicul"),
    ("Seminom", "cancer la un testicul"),
    ("Sindrom de intestin iritabil cu diaree", "colon iritabil cu diaree"),
    ("Tromboza de artera cerebrala", "dambla"),
    ("Paralizie faciala", "fata stramba"),
    ("Accident vascular cerebral", "apoplexie"),
    ("Infarct cerebral silentios", "atac cerebral"),
    ("Hemoragie cerebrala lobara", "sangerare la creier"),
    ("Psihoza", "nebunie"),
    ("Tulburare psihotica acuta", "criza de nebunie"),
    ("Raceala", "races"),
    ("Nefrocalcinoza", "nisip la rinichi"),
    ("Glomerulonefrita", "rinichi inflamat"),
    ("Nefrita interstitiala", "rinichi inflamat cu febra"),
    ("Hemoragie", "sangerare"),
    ("Hidatidoza hepatica", "chist cu apa la ficat"),
    ("Chist hepatic", "chist la ficat"),
    ("Hidrocefalie", "cap mare"),
    ("Megalencefalie", "cap prea mare"),
    ("Colecistita", "criza de fiere"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    # several folk names per condition are welcome: they are inserted one after
    # another, right after the canonical name
    popular: dict[str, list[str]] = {}

    def remember(name: str, folk: str) -> None:
        key, value = normalize(name), " ".join(folk.split())
        if not key or not value or normalize(value) in BLACKLIST:
            return
        bucket = popular.setdefault(key, [])
        if normalize(value) not in {normalize(item) for item in bucket}:
            bucket.append(value)

    for pattern in ("POP_clean.txt",):
        for path in sorted(WORK.glob(pattern)):
            for line in read_file(path):
                name, _, folk = line.partition("|")
                if name.strip() and folk.strip():
                    remember(name, folk)

    rows = [[" ".join(field.split()) for field in line.split(",")] for line in read_file(DICTIONARY)]
    index = {normalize(parts[0]): position for position, parts in enumerate(rows)}
    # a folk name may only be used when no other condition already carries it
    existing: dict[str, str] = {}
    for parts in rows:
        for term in parts:
            existing.setdefault(normalize(term), parts[0])

    overrides = 0
    missing = 0
    rejected: list[tuple[str, str, str]] = []

    # 1. central overrides win: they decide the owner of a contested folk name
    for disease, folk in OVERRIDES:
        if normalize(disease) not in index:
            missing += 1
            continue
        remember(disease, folk)
        overrides += 1

    # 2. attach folk names only where they are free
    attached: dict[str, str] = {}
    inserted = 0
    conditions_with_folk = 0
    for key, values in popular.items():
        position = index.get(key)
        if position is None:
            continue
        parts = rows[position]
        added_here = 0
        for folk in values:
            folk_key = normalize(folk)
            holder = existing.get(folk_key) or attached.get(folk_key)
            if holder and normalize(holder) != key:
                rejected.append((parts[0], folk, holder))
                continue
            if folk_key in {normalize(term) for term in parts}:
                continue
            parts.insert(1 + added_here, folk)
            attached[folk_key] = parts[0]
            added_here += 1
            inserted += 1
        if added_here:
            conditions_with_folk += 1

    print(f"folk names known             : {sum(len(v) for v in popular.values())} "
          f"for {len(popular)} conditions")
    print(f"central overrides applied    : {overrides} (diseases not found: {missing})")
    print(f"folk names inserted          : {inserted}")
    print(f"conditions carrying a folk name: {conditions_with_folk}")
    print(f"folk names owned elsewhere (skipped): {len(rejected)}")
    for disease, folk, owner in rejected[:15]:
        print(f"  skipped {disease!r}: {folk!r} already means {owner!r}")

    if args.apply:
        rows.sort(key=lambda parts: (normalize(parts[0]), parts[0]))
        DICTIONARY.write_text("\n".join(",".join(parts) for parts in rows) + "\n", encoding="utf-8")
        print(f"written: {DICTIONARY}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
