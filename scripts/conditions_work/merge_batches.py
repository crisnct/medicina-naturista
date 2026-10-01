"""Merge generated batches into data/medical_conditions.txt without duplicates.

Rules, applied in one pass over the base file plus every batch file:
  * a row whose canonical name is already in the file is the same disease: its
    synonyms are folded into the existing line, the duplicate row disappears;
  * a row that shares a synonym with an existing condition is the same disease
    under another name when the two canonical names denote one condition
    ("Mastocitoza" vs "Mastocitoza sistemica"); the names become synonyms of a
    single line. When the canonical names denote different diseases, the new row
    is dropped and reported;
  * every term therefore belongs to exactly one condition, which is what keeps
    the search unambiguous.

Usage:
  python merge_batches.py                 # dry run + report
  python merge_batches.py --apply         # rewrite the dictionary
  python merge_batches.py --popular A.txt B.txt   # also insert folk synonyms
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
DICTIONARY = ROOT / "data" / "medical_conditions.txt"
_FROM = "ăâîșțşţĂÂÎȘȚŞŢ"
_TABLE = {ord(a): b for a, b in zip(_FROM, "aaiststAAISTST")}

BATCH_ORDER = [
    "01_infectioase.txt", "02_neoplasme.txt", "03_sange_imun.txt",
    "04_endocrine_metabolice.txt", "05_psihice.txt", "06_nervos.txt",
    "07_ochi_ureche.txt", "08_circulator.txt", "09_respirator.txt",
    "10_digestiv.txt", "11_piele.txt", "12_osteoarticular.txt",
    "13_genitourinar.txt", "14_diverse.txt",
]
GENERIC = {
    "boala", "boli", "sindrom", "sindromul", "afectiune", "afectiuni", "tulburare",
    "tulburari", "acut", "acuta", "acută", "cronic", "cronica", "cronică", "primar",
    "primara", "secundar", "secundara", "de", "la", "a", "al", "ale", "din", "cu",
    "si", "sau", "in", "pe", "pentru", "tip", "forma", "the", "of", "and", "with",
}
MIN_TERMS = 2
# Two canonical names this similar are treated as one disease.
SAME_DISEASE_RATIO = 0.82


def normalize(value: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", value.translate(_TABLE).lower(), flags=re.UNICODE))


def core_tokens(value: str) -> frozenset[str]:
    return frozenset(word for word in normalize(value).split() if word not in GENERIC)


def same_disease(left: str, right: str) -> bool:
    left_key, right_key = normalize(left), normalize(right)
    if left_key == right_key:
        return True
    left_core, right_core = core_tokens(left), core_tokens(right)
    if not left_core or not right_core:
        return False
    if left_core == right_core or left_core < right_core or right_core < left_core:
        return True
    overlap = len(left_core & right_core) / min(len(left_core), len(right_core))
    if overlap >= 0.8:
        return True
    return SequenceMatcher(None, left_key, right_key).ratio() >= 0.75


class Line:
    """One condition: its terms in order, plus the text it came from."""

    def __init__(self, terms: list[str], origin: str) -> None:
        self.terms = list(terms)
        self.origin = origin

    @property
    def name(self) -> str:
        return self.terms[0]

    @property
    def keys(self) -> list[str]:
        return [normalize(term) for term in self.terms]

    def add(self, terms: list[str]) -> int:
        seen = {normalize(term) for term in self.terms}
        added = 0
        for term in terms:
            key = normalize(term)
            if key and key not in seen:
                seen.add(key)
                self.terms.append(term)
                added += 1
        return added

    def render(self) -> str:
        return ",".join(self.terms)


def read_file(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_popular(paths: list[Path]) -> dict[str, str]:
    popular: dict[str, str] = {}
    for path in paths:
        for line in read_file(path):
            if "|" not in line:
                continue
            name, _, folk = line.partition("|")
            name, folk = " ".join(name.split()), " ".join(folk.split())
            if name and folk:
                popular.setdefault(normalize(name), folk)
    return popular


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--popular", nargs="*", type=Path, default=[])
    parser.add_argument("files", nargs="*", type=Path)
    args = parser.parse_args()

    popular = read_popular(args.popular)
    batches = args.files or [WORK / name for name in BATCH_ORDER if (WORK / name).exists()]

    lines: list[Line] = []
    for text in read_file(DICTIONARY):
        lines.append(Line([" ".join(f.split()) for f in text.split(",")], "dictionary"))

    owner: dict[str, int] = {}          # normalized term -> index into lines
    name_index: dict[str, int] = {}     # normalized canonical -> index into lines
    for index, line in enumerate(lines):
        name_index.setdefault(normalize(line.name), index)
        for key in line.keys:
            owner.setdefault(key, index)

    folded_names = 0
    folded_terms = 0
    dropped: list[tuple[str, str, str]] = []      # (location, name, clash term -> owner)
    problems: list[str] = []

    for path in batches:
        for number, text in enumerate(read_file(path), 1):
            location = f"{path.name}:{number}"
            terms = [" ".join(field.split()) for field in text.split(",")]
            if any(not term for term in terms):
                problems.append(f"{location} empty field: {text[:80]}")
                continue
            if len(terms) < MIN_TERMS:
                problems.append(f"{location} fewer than {MIN_TERMS} terms: {text[:80]}")
                continue
            if len({normalize(term) for term in terms}) != len(terms):
                problems.append(f"{location} repeats a term: {text[:80]}")
                continue

            name_key = normalize(terms[0])
            target = name_index.get(name_key)
            if target is not None:
                if lines[target].add(terms):
                    folded_names += 1
                    for key in lines[target].keys:
                        owner.setdefault(key, target)
                continue

            clashes = [(term, owner[normalize(term)]) for term in terms if normalize(term) in owner]
            if clashes:
                hosts = {host_index for _, host_index in clashes}
                # a row may only fold into a line that is the same disease; if any
                # clashing line is a different disease, the shared terms stay there
                matching = sorted(host_index for host_index in hosts
                                  if same_disease(terms[0], lines[host_index].name))
                if matching:
                    target = matching[0]
                    foreign = {term_key for host_index in hosts if host_index not in matching
                               for term_key in lines[host_index].keys}
                    fresh = []
                    for term in terms:
                        key = normalize(term)
                        # keep the canonical name, and never re-add a term another line owns
                        if key == normalize(terms[0]) or key not in foreign:
                            fresh.append(term)
                    if lines[target].add(fresh):
                        folded_terms += 1
                    for key in lines[target].keys:
                        owner[key] = target
                    name_index.setdefault(normalize(lines[target].name), target)
                else:
                    dropped.append((location, terms[0], clashes[0][0]))
                continue

            index = len(lines)
            lines.append(Line(terms, path.name))
            name_index.setdefault(name_key, index)
            for key in lines[index].keys:
                owner.setdefault(key, index)

    # fold folk synonyms in, right after the canonical name of their condition
    folk_added = 0
    for index, line in enumerate(lines):
        folk = popular.get(normalize(line.name))
        if folk and normalize(folk) not in line.keys:
            line.terms.insert(1, folk)
            folk_added += 1

    lines.sort(key=lambda line: (normalize(line.name), line.name))

    # final global check: one owner per term, no duplicate canonical names
    seen_names: dict[str, str] = {}
    seen_terms: dict[str, str] = {}
    collisions = 0
    for line in lines:
        key = normalize(line.name)
        if key in seen_names:
            print(f"  !! duplicate canonical: {line.name!r} / {seen_names[key]!r}")
            collisions += 1
        seen_names.setdefault(key, line.name)
        for term in line.terms:
            term_key = normalize(term)
            if term_key in seen_terms and seen_terms[term_key] != line.name:
                print(f"  !! term {term!r} claimed by {line.name!r} and {seen_terms[term_key]!r}")
                collisions += 1
            seen_terms.setdefault(term_key, line.name)

    base_count = len(read_file(DICTIONARY))
    print(f"base lines                      : {base_count}")
    print(f"final lines                     : {len(lines)}")
    print(f"new conditions added            : {len(lines) - base_count}")
    print(f"folded as duplicate names       : {folded_names + folded_terms}")
    print(f"dropped (different disease)     : {len(dropped)}")
    print(f"folk synonyms inserted          : {folk_added}")
    print(f"remaining name/term collisions  : {collisions}")
    print(f"structural problems in batches  : {len(problems)}")
    for problem in problems[:25]:
        print(f"  [struct] {problem}")
    for location, name, term in dropped[:25]:
        print(f"  [dropped] {location}: {name!r} shares only {term!r} with a different disease")

    if args.apply:
        DICTIONARY.write_text("\n".join(line.render() for line in lines) + "\n", encoding="utf-8")
        print(f"\nwritten: {DICTIONARY}")
    return 1 if collisions else 0


if __name__ == "__main__":
    sys.exit(main())
