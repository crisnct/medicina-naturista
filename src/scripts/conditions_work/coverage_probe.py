"""Measure coverage gaps: which well-known diseases are still absent.

Read-only. Answers "is <disease> in the dictionary?" with the dictionary's own
matching rules, so it reports what a patient could not find.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.ai.conditions import load_dictionary  # noqa: E402

PROBES: dict[str, list[str]] = {
    "congenital malformations": [
        "sindrom Down", "trisomia 18", "trisomia 13", "sindrom Klinefelter", "sindrom Turner",
        "palatoschizis", "cheiloschizis", "spina bifida", "anencefalie", "hidrocefalie congenitala",
        "malformatie cardiaca congenitala", "comunicare interventriculara", "comunicare interatriala",
        "persistenta canalului arterial", "tetralogia Fallot", "coarctatie de aorta",
        "transpozitie de marile vase", "atrezie esofagiana", "atrezie intestinala",
        "malformatie anorectala", "boala Hirschsprung", "sindrom Marfan", "sindrom Ehlers-Danlos",
        "sindrom Noonan", "sindrom Prader-Willi", "sindrom Angelman", "sindrom Williams",
        "sindrom DiGeorge", "sindrom CHARGE", "sindrom VACTERL", "holoprozencefalie",
        "microcefalie", "lissencefalie", "agenzie de corp calos", "sindrom Dandy-Walker",
        "malformatie Arnold-Chiari", "polidactilie", "sindactilie", "clubfoot",
        "displazie de sold", "luxatie congenitala de sold",
    ],
    "genetic and rare": [
        "fibroza chistica", "fenilcetonurie", "boala Gaucher", "boala Niemann-Pick",
        "boala Tay-Sachs", "boala Fabry", "boala Pompe", "mucopolizaharidoza", "homocistinurie",
        "porfirie", "hemocromatoza", "boala Wilson", "deficit de alfa-1 antitripsina",
        "sindrom Li-Fraumeni", "neurofibromatoza", "scleroza tuberoasa", "ataxie Friedreich",
        "distrofie musculara Duchenne", "sindrom Rett", "sindrom fragile X",
        "anemie Fanconi", "sindrom Bloom", "xeroderma pigmentosum", "albinism",
        "osteogenesis imperfecta", "acondroplazie", "sindrom Ehlers-Danlos vascular",
    ],
    "perinatal and neonatal": [
        "icter neonatal", "asfixie perinatala", "encefalopatie hipoxico-ischemica",
        "enterocolita necrozanta", "sindrom de aspiratie de meconiu",
        "detresa respiratorie neonatala",
        "hemoragie intraventriculara", "retinopatie de prematuritate",
        "boala hemoragica neonatala",
        "sepsis neonatal", "hipoglicemie neonatala", "sifilis congenital", "rubeola congenitala",
        "toxoplasmoza congenitala", "citomegalovirus congenital", "herpes neonatal",
        "sindrom de abstinenta neonatala",
    ],
    "immune and autoinflammatory": [
        "lupus eritematos sistemic", "sclerodermie sistemica", "sindrom Sjogren",
        "poliarterita nodoza", "granulomatoza cu poliangita", "arterita Takayasu",
        "boala Behcet", "sindrom antifosfolipidic", "miastenia gravis", "polimiozita",
        "dermatomiozita", "spondilita anchilozanta", "boala Still",
        "febra mediteraneana familiala",
        "deficit de complement", "angioedem ereditar", "boala autoinflamatorie",
    ],
    "mental and neurological": [
        "schizofrenie", "tulburare bipolara", "depresie majora", "tulburare obsesiv-compulsiva",
        "scleroza multipla", "boala Parkinson", "boala Alzheimer", "epilepsie",
        "scleroza laterala amiotrofica", "migrena", "narcolepsie", "sindrom Tourette",
    ],
    "common conditions": [
        "hipertensiune arteriala", "diabet zaharat tip 2", "infarct miocardic",
        "accident vascular cerebral", "astm bronsic", "bpoc", "pneumonie", "tuberculoza",
        "hepatita C", "ciroza hepatica", "pancreatita", "boala Crohn", "colita ulcerativa",
        "psoriazis", "eczema", "acnee", "guta", "osteoporoza", "artroza", "cancer de colon",
        "cancer pulmonar", "cancer de san", "leucemie", "limfom", "anemie feripriva",
        "hipotiroidism", "hipertiroidism", "insuficienta renala cronica", "cataracta", "glaucom",
    ],
}


def main() -> int:
    dictionary = load_dictionary()
    print(f"dictionary conditions: {len(dictionary.conditions)}\n")
    total = 0
    missing_total = 0
    for area, probes in PROBES.items():
        missing = []
        for probe in probes:
            probe = " ".join(probe.split())
            total += 1
            if not dictionary.match(probe):
                missing.append(probe)
                missing_total += 1
        covered = len(probes) - len(missing)
        print(f"{area:28} {covered:3}/{len(probes):3} covered")
        for name in missing:
            print(f"      MISSING: {name}")
    print(f"\ntotal probes: {total}, missing: {missing_total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
