"""One-off: steps P1-P5 of the ICD-10 plan for one letter.

Reads tmp/icd10_work/icd10_ro.jsonl and medicina-naturista-documente/data/medical_conditions.jsonl, keeps the
codes whose Romanian title starts with the letter (diacritics folded), drops the
residual / non-disease titles, and matches the rest against the dictionary:

  exista  - exact term, temporal variant (G1) or the same words once Romanian
            endings are folded (Anemia = Anemie, Erizipelul = Erizipel);
  posibil - shares its key words with an existing condition, or spells close to
            one: decided by hand (G4, G5);
  nou     - nothing alike in the dictionary;
  eliminat- with the reason (P2).

Writes tmp/icd10_work/candidates_<L>.jsonl and a readable candidates_<L>.txt.

Run:  python src/scripts/icd10_work/match_letter.py A
"""
from __future__ import annotations

import json
import re
import sys
from difflib import SequenceMatcher, get_close_matches
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from backend.ai.conditions import _fold_word, _normalize, parse_conditions  # noqa: E402

WORK = ROOT / "tmp" / "icd10_work"
SOURCE = WORK / "icd10_ro.jsonl"
DICTIONARY = ROOT / "medicina-naturista-documente" / "data" / "medical_conditions.jsonl"

MODALITIES = {"acut", "acuta", "acute", "subacut", "subacuta", "subacute", "cronic", "cronica",
              "cronice", "recurent", "recurenta", "recurente", "recidivant", "recidivanta"}
GENERIC = {
    "boala", "boli", "bolile", "sindrom", "sindromul", "afectiune", "afectiuni", "tulburare",
    "tulburari", "tulburarea", "acut", "acuta", "cronic", "cronica", "primar", "primara",
    "secundar", "secundara", "de", "la", "a", "al", "ale", "din", "cu", "si", "sau", "in", "pe",
    "pentru", "tip", "forma", "prin", "datorita", "datorat", "datorate", "fara", "alte", "the",
    "of", "and", "with",
}
QUALIFIERS = [
    r",?\s*neclasificat[aei]? (?:in alta parte|altundeva)",
    r",?\s*fara (?:alta|alte) specifica[tr]i[ea]",
    r",?\s*nespecificat[aeiu]?l?\b",
    r"\bNOS\b",
    r",?\s*NCA\b",
]
DROP_PREFIXES = {
    "rezidual": ("alte ", "alti ", "alta ", "altele", "alt ", "diverse ", "unele ", "anumite "),
    "factor/ingrijire": ("antecedente", "rezultate anormale", "ingrijiri acordate", "ingrijire ",
                         "supraveghere", "examinare", "examen ", "screening", "purtator"),
    "fat afectat de mama": ("fat si nou-nascut afectat", "fat sau nou-nascut afectat",
                            "fat si nou nascut afectat"),
    "sechele": ("sechele", "sechela"),
}
DROP_CONTAINS = {
    "asterisc (in alte boli)": ("in boli clasificate", "in alte boli clasificate", "in bolile clasificate",
                                "in boli infectioase si parazitare clasificate"),
    "agent cauzal, nu boala": ("cauza unor boli clasificate", "cauza a unor boli clasificate",
                               "drept cauza a", "ca si cauza a"),
    "procedura": ("postprocedural", "dupa procedur", "dupa interventi", "dupa o procedur",
                  "consecutiv unei proceduri", "consecutive unei proceduri"),
}
# A title that is only a bucket of the classification ("Afectiuni ale venelor",
# "Anomalii ale pleurei"), not one named disease.
GENERIC_HEADS = re.compile(
    r"^(afectiun\w*|tulburar\w*|boli|bolile|anomali\w*|anormalitat\w*|leziun\w*|probleme|stari|"
    r"defecte|malformati\w*|complicati\w*|infectii|inflamati\w*)"
    r"( (inflamatori\w*|neinflamatori\w*|degenerativ\w*|vascular\w*|functional\w*|congenital\w*|"
    r"ereditar\w*|cronic\w*|acut\w*|nereumati\w*|hipertrofic\w*|atrofic\w*|granulomatoas\w*|"
    r"localizat\w*|neinfectioas\w*|toxic\w*|majore|minore|partiale|combinate|specifice))*"
    r" (ale|al|a|ai|de|in|asociat\w*|legat\w*|interesand)"
)
# Subdivisions that only add a complication, a side or a duration to their category (D5).
VARIANT_WORDS = re.compile(r"(cu|fara|unilateral\w*|bilateral\w*|dreapt\w*|stang\w*|durata)")
NEOPLASM_WORDS = ("tumor", "carcinom", "sarcom", "leucemi", "limfom", "melanom", "mielom", "adenom",
                  "neoplasm", "cancer", "blastom", "gliom", "lipom", "fibrom", "hemangiom", "nev",
                  "papilom", "polip", "chist", "boala", "sindrom", "histiocit", "mastocit", "plasmocitom")


def plain_letter(title: str) -> str:
    normalized = _normalize(title)
    return normalized[:1].upper()


def strip_qualifiers(title: str) -> str:
    text = title
    for pattern in QUALIFIERS:
        text = re.sub(pattern, "", text, flags=re.I)
    text = re.sub(r"\((?:[^()]*\d[^()]*)\)", "", text)        # code references "(A41.9)"
    text = re.sub(r"\s+", " ", text).strip(" ,;.-")
    return text


def aliases(row: dict) -> list[str]:
    """The title, its bracketed / parenthesised alternatives and the short inclusion terms."""
    title = row["title_ro"]
    found = [strip_qualifiers(re.sub(r"[\[(][^\])]*[\])]", "", title))]
    for inner in re.findall(r"[\[(]([^\])]+)[\])]", title):
        if not re.search(r"\d", inner) and len(inner) > 3:
            found.append(strip_qualifiers(inner))
    for item in row["inclusions"]:
        item = strip_qualifiers(item)
        if 3 < len(item) <= 70 and not re.search(r"\d|vezi|capitol", item, re.I) and not item.endswith(":"):
            found.append(item)
    return [term for term in dict.fromkeys(found) if term]


def folded(text: str) -> tuple[str, ...]:
    return tuple(_fold_word(word) for word in _normalize(text).split())


def core(text: str) -> frozenset[str]:
    return frozenset(_fold_word(word) for word in _normalize(text).split() if word not in GENERIC)


def drop_reason(row: dict, parent: dict | None) -> str | None:
    title = _normalize(row["title_ro"])
    if not title or not title[0].isalpha():
        return "titlu invalid"
    for reason, prefixes in DROP_PREFIXES.items():
        if title.startswith(prefixes):
            return reason
    for reason, needles in DROP_CONTAINS.items():
        if any(needle in title for needle in needles):
            return reason
    if row["chapter"] == "II" and len(row["code"]) > 3 and not any(word in title for word in NEOPLASM_WORDS):
        return "subzona de organ (D5)"
    stripped = strip_qualifiers(row["title_ro"])
    if not stripped:
        return "rezidual"
    if GENERIC_HEADS.match(_normalize(stripped)) or _normalize(stripped).split()[0] in {"afectiuni", "afectiune", "anomalii"}:
        return "categorie generica (nu o boala anume)"
    if parent is not None:
        parent_words = folded(strip_qualifiers(parent["title_ro"]))
        if folded(stripped) == parent_words:
            return "dublura categoriei parinte (nespecificat)"
        if (len(parent_words) >= 1 and folded(stripped)[:len(parent_words)] == parent_words
                and VARIANT_WORDS.search(_normalize(stripped)[len(" ".join(parent_words)):])):
            return "varianta a categoriei (D5)"
    return None


class Dictionary:
    def __init__(self) -> None:
        self.conditions = parse_conditions(DICTIONARY.read_text(encoding="utf-8"))
        self.by_term: dict[str, str] = {}
        self.by_folded: dict[tuple[str, ...], str] = {}
        self.by_core: dict[frozenset[str], set[str]] = {}
        for condition in self.conditions:
            for term in condition.terms:
                self.by_term.setdefault(_normalize(term), condition.name)
                self.by_folded.setdefault(folded(term), condition.name)
                key = core(term)
                if key:
                    self.by_core.setdefault(key, set()).add(condition.name)
        self.terms = list(self.by_term)

    def exact(self, term: str) -> tuple[str, str] | None:
        key = _normalize(term)
        if key in self.by_term:
            return "exact", self.by_term[key]
        words = folded(term)
        if words in self.by_folded:
            return "terminatii", self.by_folded[words]
        trimmed = list(words)
        while trimmed and trimmed[-1] in {_fold_word(m) for m in MODALITIES}:
            trimmed.pop()
        if trimmed and tuple(trimmed) != words and tuple(trimmed) in self.by_folded:
            return "temporal (G1)", self.by_folded[tuple(trimmed)]
        return None

    def similar(self, term: str) -> list[str]:
        found: list[str] = []
        key = core(term)
        if key:
            found.extend(sorted(self.by_core.get(key, ())))
            if len(key) >= 2:
                for other, names in self.by_core.items():
                    if len(other) >= 2 and (key < other or other < key) and len(key & other) >= 2:
                        found.extend(sorted(names))
        for close in get_close_matches(_normalize(term), self.terms, n=3, cutoff=0.8):
            found.append(self.by_term[close])
        return list(dict.fromkeys(found))[:6]


def main() -> int:
    letter = sys.argv[1].upper()
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_code = {row["code"]: row for row in rows}
    dictionary = Dictionary()
    results: list[dict] = []
    for row in rows:
        if plain_letter(row["title_ro"]) != letter:
            continue
        parent = by_code.get(row["code"][:3]) if len(row["code"]) > 3 else None
        result = {"code": row["code"], "title_ro": row["title_ro"], "title_en": row["title_en"],
                  "parent": parent["title_ro"] if parent else "", "aliases": aliases(row)}
        reason = drop_reason(row, parent)
        if reason:
            result.update(verdict="eliminat", reason=reason)
        else:
            english = [row["title_en"]] if row["title_en"] else []
            hit = next((found for term in result["aliases"] + english if (found := dictionary.exact(term))), None)
            if hit:
                result.update(verdict="exista", level=hit[0], condition=hit[1])
            else:
                similar = list(dict.fromkeys(name for term in result["aliases"][:2] for name in dictionary.similar(term)))
                if similar:
                    result.update(verdict="posibil", similar=similar[:6])
                else:
                    result.update(verdict="nou")
        results.append(result)

    out = WORK / f"candidates_{letter}.jsonl"
    with out.open("w", encoding="utf-8", newline="\n") as handle:
        for result in results:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
    with (WORK / f"candidates_{letter}.txt").open("w", encoding="utf-8", newline="\n") as handle:
        for verdict in ("nou", "posibil", "exista", "eliminat"):
            chosen = [result for result in results if result["verdict"] == verdict]
            handle.write(f"===== {verdict.upper()} ({len(chosen)})\n")
            for result in chosen:
                extra = {
                    "nou": "",
                    "posibil": " ~ " + " | ".join(result.get("similar", [])),
                    "exista": f" = {result.get('condition')} [{result.get('level')}]",
                    "eliminat": f" [{result.get('reason')}]",
                }[verdict]
                alt = [term for term in result["aliases"][1:]]
                alt_text = f"  {{{' / '.join(alt)}}}" if alt and verdict in ("nou", "posibil") else ""
                english = f"  <{result['title_en']}>" if verdict in ("nou", "posibil") and result["title_en"] else ""
                handle.write(f"{result['code']:7} {result['title_ro']}{alt_text}{english}{extra}\n")
    counts = {verdict: sum(1 for result in results if result["verdict"] == verdict)
              for verdict in ("nou", "posibil", "exista", "eliminat")}
    print(f"{letter}: {len(results)} codes  {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
