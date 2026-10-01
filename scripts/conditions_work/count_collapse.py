"""Count how many conditions collapse under each "variant" rule.

Read-only analysis, so the scope of the collapse can be agreed before applying it.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_batches import DICTIONARY, normalize, read_file  # noqa: E402

# modifiers that mark a variant of the same disease
ACUTE = ("acut", "acuta", "acute")
CHRONIC = ("cronic", "cronica", "chronic")
SUBTYPES = {
    "acut": {"acut", "acuta", "subacut", "subacuta", "acutizat", "acutizata"},
    "cronic": {"cronic", "cronica", "recurent", "recurenta", "persistent", "persistenta"},
}
GRADES = {"usor", "usoara", "moderat", "moderata", "sever", "severa", "light", "mild",
          "moderate", "severe", "grad", "stadiu", "stadium"}
SITES = {
    "abdominal", "abdominala", "axilar", "axilara", "cerebelos", "cerebral", "cerebrala",
    "cornean", "cutanat", "cutanata", "dentar", "epidural", "gastric", "gastrica", "hepatic",
    "hepatobiliar", "hipofizar", "intestinal", "intestinala", "mamar", "mamara", "mandibular",
    "maxilar", "mediastinal", "miocardic", "ocular", "orbital", "pancreatic", "parafaringian",
    "pelvin", "perianal", "perirectal", "perirenal", "peritoneal", "peritonsilar", "pilonidal",
    "pleural", "prostatic", "psoas", "pulmonar", "pulmonara", "renal", "renala", "retinian",
    "retroperitoneal", "sinusal", "spinal", "splenic", "subcutanat", "subfrenic", "tiroidian",
    "tiroidiana", "vertebral", "vaginal", "vulvar", "uterin", "uterina", "ovarian", "ovarianа",
    "esofagian", "gastric", "colonic", "rectal", "ileal", "jejunal", "cecal", "anal", "labial",
    "lingual", "nazal", "oral", "gingival", "salivar", "tubar", "ureteral", "uretral", "vezical",
    "timic", "pineal", "parotidian", "paratiroidian", "suprarenal", "adrenal", "conjunctival",
    "bronhiolar", "bronsic", "faringian", "laringian", "nazofaringian", "distal", "cervical",
    "toracic", "lombar", "sacrat", "iliac", "femural", "tibial", "peroneu", "radial", "ulnar",
    "median", "optic", "opticа", "acustic", "vestibular", "cortical", "medular", "pontin",
    "cerebelar", "hypofizar", "splenic", "hepatobiliar",
}
ORGANS = {"ficat", "rinichi", "stomac", "plamani", "inima", "creier", "splina", "pancreas",
          "vezica", "prostata", "uter", "ovar", "testicul", "tiroida", "san", "colon", "rect",
          "esofag", "laringe", "faringe", "nas", "ureche", "ochi", "piele", "os", "muschi",
          "nerv", "ganglion", "ganglioni", "vase", "artera", "vena"}
SEVERITY_TAIL = re.compile(
    r"\b(usor|usoara|moderat|moderata|sever|severa|grad|stadiu|stadium|mild|moderate|severe|"
    r"light|tip|type|stadiul|faza|faze|forma|forme)\b", re.IGNORECASE)


def body_tokens(name: str) -> list[str]:
    return normalize(name).split()


def acute_or_chronic_variant(name: str, base: str) -> bool:
    """base + one acute/chronic modifier, and nothing else."""
    tokens = body_tokens(name)
    base_tokens = body_tokens(base)
    if tokens[:len(base_tokens)] != base_tokens:
        return False
    rest = set(tokens[len(base_tokens):])
    if not rest:
        return False
    return rest <= (SUBTYPES["acut"] | SUBTYPES["cronic"])


def has_other_qualifier(name: str, base: str) -> bool:
    tokens = body_tokens(name)
    base_tokens = body_tokens(base)
    rest = tokens[len(base_tokens):] if tokens[:len(base_tokens)] == base_tokens else tokens
    return any(token in SITES | ORGANS or token.isdigit() for token in rest)


def main() -> int:
    rows = [line.split(",")[0].strip() for line in read_file(DICTIONARY)]
    names = {normalize(name) for name in rows}
    groups: dict[str, list[str]] = defaultdict(list)
    for name in rows:
        key = normalize(name)
        tokens = body_tokens(name)
        for size in range(1, len(tokens)):
            candidate = " ".join(tokens[:size])
            if candidate in names:
                groups[candidate].append(name)
                break

    collapse_acute_chronic = []
    collapse_grades = []
    collapse_sites = []
    for base, members in groups.items():
        if len(members) < 2:
            continue
        ac = [m for m in members if acute_or_chronic_variant(m, base)]
        if len(ac) >= 1 and not any(has_other_qualifier(m, base) for m in ac):
            collapse_acute_chronic.append((base, ac))
        elif any(SEVERITY_TAIL.search(" ".join(body_tokens(m)[len(body_tokens(base)):]))
                 for m in members):
            collapse_grades.append((base, members))
        elif any(has_other_qualifier(m, base) for m in members):
            collapse_sites.append((base, members))

    def total(items: list[tuple[str, list[str]]]) -> int:
        return sum(len(members) for _, members in items)

    print(f"conditions in file                          : {len(rows)}")
    print(f"families (base + variants)                  : {len(groups)}")
    print()
    print(f"A) base + only 'acut/cronic/subacut/recurent': {len(collapse_acute_chronic):4d} families,"
          f" {total(collapse_acute_chronic):5d} variants -> collapse to {len(collapse_acute_chronic)} lines"
          f" ({total(collapse_acute_chronic) - len(collapse_acute_chronic)} removed)")
    print(f"B) base + severity/grade/type wording       : {len(collapse_grades):4d} families,"
          f" {total(collapse_grades):5d} variants")
    print(f"C) base + organ/site qualifier              : {len(collapse_sites):4d} families,"
          f" {total(collapse_sites):5d} variants")
    print()
    print("examples of A (safe, exactly your Amigdalita case):")
    for base, members in sorted(collapse_acute_chronic, key=lambda item: -len(item[1]))[:12]:
        print(f"   {base!r} <- {members}")
    print()
    print("examples of C (organ/site variants):")
    for base, members in sorted(collapse_sites, key=lambda item: -len(item[1]))[:4]:
        print(f"   {base!r} <- {len(members)} members, e.g. {members[:6]}")
    print()
    print("examples of B (grade/severity):")
    for base, members in sorted(collapse_grades, key=lambda item: -len(item[1]))[:4]:
        print(f"   {base!r} <- {members[:6]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
