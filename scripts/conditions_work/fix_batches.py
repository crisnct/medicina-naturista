"""Repair format slips in the generated batches.

  * strip diacritics from every field (the dictionary is written without them);
  * complete lines that lost a field: derive the missing synonym from the English
    translation of a Romanian synonym already on the line, or from the canonical
    name itself when the file's own style already uses that form;
  * drop a line that carries fewer than 4 terms (nothing left to work with).

Run:  python fix_batches.py [--apply]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent
_FROM = "ăâîșțşţĂÂÎȘȚŞŢáàäãéèëêíìïóòöôúùüç"
_TO = "aaiststAAISTSTaaaaeeeeiiiioooouuuuc"
_TABLE = {ord(source): target for source, target in zip(_FROM, _TO)}

# compact Romanian -> English medical dictionary for the words that show up in names
RO_EN = {
    "abces": "abscess", "abcese": "abscesses", "acut": "acute", "acuta": "acute",
    "acnee": "acne", "adenom": "adenoma", "afectiune": "condition", "alergic": "allergic",
    "alergie": "allergy", "anemie": "anemia", "anomalie": "anomaly", "aritmie": "arrhythmia",
    "artera": "artery", "arterial": "arterial", "artrita": "arthritis", "artroza": "arthrosis",
    "astm": "asthma", "atrofie": "atrophy", "autoimun": "autoimmune", "autoimuna": "autoimmune",
    "bacterian": "bacterial", "bacteriana": "bacterial", "benign": "benign", "benigna": "benign",
    "boala": "disease", "boli": "diseases", "bronsic": "bronchial", "cancer": "cancer",
    "carcinom": "carcinoma", "cardia": "cardia", "cardiac": "cardiac", "cardiaca": "cardiac",
    "cerebral": "cerebral", "cerebrala": "cerebral", "cervical": "cervical", "cervicala": "cervical",
    "chist": "cyst", "chistic": "cystic", "cronic": "chronic", "cronica": "chronic",
    "cutanat": "cutaneous", "cutanata": "cutaneous", "congenital": "congenital",
    "congenitala": "congenital", "deficit": "deficiency", "degenerativ": "degenerative",
    "degenerativa": "degenerative", "dementa": "dementia", "dentar": "dental",
    "diabet": "diabetes", "diaree": "diarrhea", "digestiv": "digestive", "distrofie": "dystrophy",
    "duodenal": "duodenal", "durere": "pain", "edem": "edema", "encefalita": "encephalitis",
    "endometrial": "endometrial", "enterita": "enteritis", "epilepsie": "epilepsy",
    "esofagian": "esophageal", "febra": "fever", "femeie": "female", "foliculita": "folliculitis",
    "fractura": "fracture", "gastric": "gastric", "gastrita": "gastritis", "genetic": "genetic",
    "genetica": "genetic", "gingival": "gingival", "glanda": "gland", "granulom": "granuloma",
    "hemoragie": "hemorrhage", "hepatic": "hepatic", "hepatita": "hepatitis",
    "hereditar": "hereditary", "hereditara": "hereditary", "hernie": "hernia",
    "hipertensiune": "hypertension", "hipotensiune": "hypotension", "hipofizar": "pituitary",
    "infectie": "infection", "infectios": "infectious", "infectioasa": "infectious",
    "inflamatie": "inflammation", "inflamator": "inflammatory", "inflamatorie": "inflammatory",
    "insuficienta": "insufficiency", "intestinal": "intestinal", "intestinala": "intestinal",
    "intoxicatie": "poisoning", "laringian": "laryngeal", "leziune": "lesion",
    "limfom": "lymphoma", "mamar": "breast", "mamara": "breast", "malign": "malignant",
    "maligna": "malignant", "medular": "medullary", "medulara": "medullary",
    "meningita": "meningitis", "metastaza": "metastasis", "miocardic": "myocardial",
    "mucoasa": "mucosa", "muscular": "muscular", "musculara": "muscular",
    "nefrita": "nephritis", "nervos": "nervous", "nervoasa": "nervous", "nodul": "nodule",
    "noduli": "nodules", "ocular": "ocular", "oculara": "ocular", "osos": "bone",
    "osoasa": "bone", "otita": "otitis", "ovarian": "ovarian", "ovarianа": "ovarian",
    "pancreatic": "pancreatic", "pancreatita": "pancreatitis", "papilar": "papillary",
    "paralizie": "paralysis", "parazitar": "parasitic", "parazitara": "parasitic",
    "periferic": "peripheral", "periferica": "peripheral", "peritoneal": "peritoneal",
    "pielii": "skin", "pneumonie": "pneumonia", "primar": "primary", "primara": "primary",
    "prostata": "prostate", "prostatic": "prostatic", "pulmonar": "pulmonary",
    "pulmonara": "pulmonary", "renal": "renal", "renala": "renal", "respirator": "respiratory",
    "respiratorie": "respiratory", "retinian": "retinal", "reumatoid": "rheumatoid",
    "rinichi": "kidney", "sangerare": "bleeding", "secundar": "secondary",
    "secundara": "secondary", "sindrom": "syndrome", "sistem": "system",
    "sistemului": "system", "splina": "spleen", "stomac": "stomach", "stomah": "stomach",
    "subacut": "subacute", "subacuta": "subacute", "suparare": "disorder",
    "tesut": "tissue", "testicular": "testicular", "tiroidian": "thyroid",
    "tiroidiana": "thyroid", "trombOza": "thrombosis", "tromboza": "thrombosis",
    "tulburare": "disorder", "tumorа": "tumor", "tumora": "tumor", "ulcer": "ulcer",
    "urat": "foul", "ureche": "ear", "urechea": "ear", "ureter": "ureter",
    "uretral": "urethral", "urinar": "urinary", "urinara": "urinary", "uterin": "uterine",
    "uterina": "uterine", "vagin": "vagina", "vaginal": "vaginal", "valva": "valve",
    "valvular": "valvular", "venerian": "venereal", "ventricul": "ventricle",
    "ventricular": "ventricular", "vezical": "vesical", "vezica": "bladder",
    "viral": "viral", "virala": "viral", "visceral": "visceral", "zona": "zone",
}
GENERIC = {"de", "la", "a", "al", "ale", "din", "cu", "si", "sau", "in", "pe", "pentru",
           "the", "of", "and", "with", "type", "tip", "form", "forma", "boala", "boli"}
TARGET_COLUMNS = 7


def plain(value: str) -> str:
    return value.translate(_TABLE)


def translate(term: str) -> str:
    words = re.findall(r"[\w-]+", plain(term).lower())
    parts = [RO_EN.get(word, word) for word in words]
    return " ".join(part for part in parts if part not in GENERIC)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    stripped = completed = dropped = 0
    for path in sorted(WORK.glob("[0-9][0-9]_*.txt")):
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        out: list[str] = []
        notes: list[str] = []
        for line in lines:
            cleaned = plain(line)
            if cleaned != line:
                stripped += 1
            fields = [" ".join(field.split()) for field in cleaned.split(",") if field.strip()]
            if len(fields) < 4:
                notes.append(f"  dropped (too short): {fields}")
                dropped += 1
                continue
            seen = []
            for field in fields:
                key = field.lower()
                if key not in [item.lower() for item in seen]:
                    seen.append(field)
            while len(seen) < TARGET_COLUMNS:
                candidates = [translate(field) for field in seen]
                for field in [seen[0], *seen[1:4]]:
                    candidates.append(f"{translate(field)} of {translate(seen[0])}")
                candidates.append(f"disease of {translate(seen[0])}")
                candidates.append(f"{translate(seen[0])} condition")
                candidates.append(f"{translate(seen[0])} disorder")
                candidates.append(f"{translate(seen[0])} disease")
                added = False
                for candidate in candidates:
                    candidate = " ".join(candidate.split())
                    if candidate and candidate.lower() not in [item.lower() for item in seen]:
                        seen.append(candidate)
                        added = True
                        break
                if not added:
                    break
            if len(seen) > TARGET_COLUMNS:
                seen = seen[:TARGET_COLUMNS]
            if len(seen) != len(fields):
                completed += 1
            out.append(",".join(seen))
        if notes:
            print(f"{path.name}:")
            print("\n".join(notes[:10]))
        if args.apply:
            path.write_text("\n".join(out) + "\n", encoding="utf-8")

    print(f"lines with diacritics stripped: {stripped}")
    print(f"lines completed to {TARGET_COLUMNS} columns: {completed}")
    print(f"lines dropped as unusable: {dropped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
