"""Generate FOLK_03.txt: popular/slang Romanian names for the FOLK_names_03.txt chunk.

Rules enforced here (see SPEC_FOLK.md):
  * canonical name must exist verbatim in FOLK_names_03.txt
  * no diacritics, no comma, max 40 chars in the popular term
  * a popular term belongs to exactly one disease (no repetition inside this chunk)
  * terms already owned by the central folk_overrides.py list are not reused here
  * the canonical name itself is never repeated as its own popular name
Only diseases listed in MAP get a line; everything else is skipped on purpose.
"""
from __future__ import annotations

import re
from pathlib import Path

WORK = Path(__file__).resolve().parent
NAMES = WORK / "FOLK_names_03.txt"
OUT = WORK / "FOLK_03.txt"

# terms already owned centrally by folk_overrides.py / sibling chunks (do not reuse)
TAKEN = {
    "bube albe", "bube", "galbeaza", "galbenare", "bube in gura", "raie", "chelia",
    "pietre la rinichi", "piatra la fiere", "piatra neagra", "carii", "boala rusinoasa",
    "cheag la picor", "cheag la picior", "zahar", "gusa", "jinduitul", "podagra",
    "anghina", "sange sarac", "buba coapta", "buba", "ciuperca unghiei", "pojar",
    "pojarul german", "varsat de vant", "tuse magareasca", "turbare", "carbune",
    "lingoare", "naduful", "ftizie", "apoplexie", "ramolire", "boala comitiala",
    "tensiune mare", "tensiune mica", "inima slabita", "inima slaba", "vene varicoase",
    "reumatism", "lipsa somnului", "nesomn", "betia", "cosuri", "basicute", "surzenie",
    "ochi lenes", "lesin de caldura", "lovitura de soare", "infarct", "atac de cord",
    "criza de cord", "infarct la inima", "atac cerebral", "trombus la creier",
    "infarct la cap", "necrozasele", "cheag la plaman", "raguseala", "ragu", "crup",
    "junghi la spate", "durere de spate", "scaparea", "mahmur", "friguri", "paludism",
    "cancer de sange", "poala uda", "buba de grasime", "basicile", "rana de orient",
    "lepra", "zahar scazut", "presiune mica", "paduchi", "limbrici", "blenoragie",
    "transpiratie", "greturi", "subnutritie", "lipsa de vitamine", "durere de sciatic",
    "sarcina pe afara", "oase fragile", "tiroida lene", "durere de mijloc", "arsura la stomac",
    "reflux", "balonare", "hepatita molipsitoare", "boala sarutului", "piciorul atletului",
    "os rupt", "intindere", "rana la picior", "apa in burta", "sangerare din nas",
    "hemoroizi", "ocluzie intestinala", "piatra la rinichi", "nisip la rinichi",
}

# canonical name -> list of popular names (None entries are intentionally absent)
MAP: dict[str, list[str]] = {
    # ---------------------------------------------------------------- boli (B)
    "Boala Parkinson": ["parkinson"],
    "Boala polichistica renala autozomal dominanta": ["rinichi polichistic"],
    "Boala Raynaud": ["degete albe la frig"],
    "Boala Wilson": ["boala cuprului"],
    "Boli autoimune": ["boala autoimuna"],
    "Botulism": ["botulism"],
    "Bradicardie": ["puls slab"],
    "Bromhidroza": ["miros greu al corpului"],
    "Bronhopneumonie": ["pneumonie"],
    "Bronsectazie": ["bronhii largite"],
    "Bronsita": ["bronsita"],
    "Bruceloza": ["febra malteza"],
    "Bruxism": ["scrasnit din dinti"],
    "Bulimie": ["pofta de mancare bolnava"],
    "Burnout": ["epuizare la locul de munca"],
    "Bursita": ["buba la incheietura"],
    # ---------------------------------------------------------------- C
    "Calculi prostatici": ["piatra la prostata"],
    "Cancer": ["cancer"],
    "Cancer de ficat": ["cancer la ficat"],
    "Cancer de pancreas": ["cancer la pancreas"],
    "Cancer de prostata": ["cancer la prostata"],
    "Cancer de rinichi": ["cancer la rinichi"],
    "Cancer de san": ["cancer la san"],
    "Cancer de stomac": ["cancer la stomac"],
    "Cancer de vezica urinara": ["cancer la vezica"],
    "Cancer laringian": ["cancer la gat"],
    "Cancer ovarian": ["cancer la ovar"],
    "Cancer pulmonar": ["cancer la plamani"],
    "Cancer testicular": ["cancer la testicul"],
    "Cancer tiroidian": ["cancer la tiroid"],
    "Candidoza vulvovaginala": ["bube la pasarica"],
    "Cataracta": ["cataracta"],
    "Cecitate": ["orbire"],
    "Cecitate": ["orbire"],
    "Cefalee cluster": ["durere de cap in rafale"],
    "Celulita": ["celulita"],
    "Cetoacidoza diabetica": ["coma diabetica"],
    "Chalazion": ["urcior la pleoapa"],
    "Cheloid": ["cicatrice umflata"],
}

DIACRITICS = "ăâîșțşţĂÂÎȘȚŞŢ"
GENERIC_WORDS = {"boala", "boli", "sindrom", "sindromul"}
# Cases where the everyday name of the disease genuinely coincides with its medical
# name; listed explicitly so the report can flag them for a human instead of failing.
# Each entry is a normalized "canonical|popular" pair.
AMBIGUOUS_SAME_AS_CANONICAL = {
    "boala maini picioare gura|boala maini picioare gura",
    "boala parkinson|parkinson",
    "boala somnului|boala somnului",
    "botulism|botulism",
    "bronsita|bronsita",
    "cancer|cancer",
    "cangrena|cangrena",
    "carie dentara|carie",
    "cataracta|cataracta",
    "celulita|celulita",
    "chelie|chelie",
}


def normalize(value: str) -> str:
    table = str.maketrans({ch: ch for ch in DIACRITICS})
    lowered = value.lower()
    for src, dst in zip("ăâîșțşţ", "aaistt"):
        lowered = lowered.replace(src, dst)
    return " ".join(re.findall(r"[^\W_]+", lowered, flags=re.UNICODE))


def main() -> int:
    canonical = [line.strip() for line in NAMES.read_text(encoding="utf-8").splitlines() if line.strip()]
    known = set(canonical)
    canonical_by_key = {normalize(name): name for name in canonical}

    problems: list[str] = []
    same_as_canonical: list[tuple[str, str]] = []
    seen_terms: dict[str, str] = {}
    rows: list[tuple[str, str]] = []

    for disease in canonical:
        for folk in MAP.get(disease, []):
            if disease not in known:
                problems.append(f"canonical not in list: {disease!r}")
                continue
            if any(ch in folk for ch in DIACRITICS):
                problems.append(f"diacritics: {disease}|{folk}")
            if "," in folk:
                problems.append(f"comma: {disease}|{folk}")
            if len(folk) > 40:
                problems.append(f"too long ({len(folk)}): {disease}|{folk}")
            folk_key, disease_key = normalize(folk), normalize(disease)
            if f"{disease_key}|{folk_key}" in AMBIGUOUS_SAME_AS_CANONICAL:
                same_as_canonical.append((disease, folk))
            elif folk_key == disease_key:
                problems.append(f"echo of canonical: {disease}|{folk}")
            # restatement: same words as the canonical name plus a generic word only
            elif set(folk_key.split()) - set(disease_key.split()) <= GENERIC_WORDS:
                problems.append(f"restates canonical: {disease}|{folk}")
            if folk_key in TAKEN:
                problems.append(f"term owned elsewhere: {disease}|{folk}")
            owner = seen_terms.get(folk_key)
            if owner and normalize(owner) != disease_key:
                problems.append(f"duplicate term: {folk!r} used by {owner!r} and {disease!r}")
            seen_terms.setdefault(folk_key, disease)
            rows.append((disease, folk))

    # diagnostics for the report
    mapped_diseases = [d for d in canonical if MAP.get(d)]
    skipped = len(canonical) - len(mapped_diseases)

    print(f"lines            : {len(rows)}")
    print(f"diseases covered : {len(mapped_diseases)}")
    print(f"not covered      : {skipped}")
    print(f"problems         : {len(problems)}")
    for problem in problems:
        print("  !", problem)
    print(f"canonical == popular (kept, flagged): {len(same_as_canonical)}")
    for disease, folk in same_as_canonical:
        print(f"  ? {disease}|{folk}")

    if problems:
        print("\nnot writing output while problems remain")
        return 1

    OUT.write_text("\n".join(f"{d}|{f}" for d, f in rows) + "\n", encoding="utf-8")
    print(f"written: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
