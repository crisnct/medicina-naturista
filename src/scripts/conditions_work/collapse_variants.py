"""Collapse acute/chronic variants of one disease into a single line.

  Amigdalita (base) + Amigdalita acuta + Amigdalita cronica -> Amigdalita
  Bronsita acuta + Bronsita cronica (no base)               -> Bronsita

The canonical name is the general form (never the "acut"/"cronic" one) and every
synonym of every variant is kept, with the time forms placed first because they
are the most specific search terms.

Two safeguards, so that only genuine time variants merge:

  * the modality is read from the CANONICAL name only. A synonym like
    `ulcer duodenal cronic` (a synonym of `Ulcer duodenal`) never creates a
    variant, which is what keeps `Ulcer duodenal` and `Ulcer gastric` apart;
  * a family is collapsed only when its members share the same stem after the
    modality is removed, so `Colita amibiana` and `Colita ulcerativa` (different
    stems, different diseases) stay separate.

Organ/site variants (`Abces renal`, `Cancer de colon`, `Anemie aplastica`) are
never touched.

Run:  python collapse_variants.py [--apply]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent
sys.path.insert(0, str(WORK))
from merge_batches import DICTIONARY, normalize, read_file  # noqa: E402

MODALITIES: dict[str, set[str]] = {
    "acut": {"acut", "acuta", "acute"},
    "subacut": {"subacut", "subacuta", "subacute"},
    "cronic": {"cronic", "cronica", "cronice", "chronic"},
    "recurent": {"recurent", "recurenta", "recurrent", "recidivant", "recidivanta"},
}
TAIL_TO_MODALITY = {tail: name for name, tails in MODALITIES.items() for tail in tails}
# word order used when the time forms are placed first on the collapsed line
MODALITY_ORDER = ("acut", "subacut", "cronic", "recurent")


def split_modality(name: str) -> tuple[str, str] | None:
    """('Amigdalita acuta') -> ('amigdalita', 'acut'); None when there is no modality."""
    tokens = normalize(name).split()
    if len(tokens) < 2:
        return None
    modality = TAIL_TO_MODALITY.get(tokens[-1])
    if not modality:
        return None
    return " ".join(tokens[:-1]), modality


def display_form(stem: str, members: list[list[str]]) -> str:
    """The stem written the way the dictionary spells it elsewhere, capitalised."""
    wanted = set(stem.split())
    for parts in members:
        tokens = normalize(parts[0]).split()
        if set(tokens) == wanted and len(tokens) == len(wanted):
            return parts[0]
    for parts in members:
        for term in parts:
            tokens = normalize(term).split()
            if set(tokens) == wanted and len(tokens) == len(wanted):
                return term[:1].upper() + term[1:]
    return stem[:1].upper() + stem[1:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--generalize-single", action="store_true",
                        help="also rename a lone variant without a base (Hepatita cronica -> Hepatita)")
    args = parser.parse_args()

    rows = [[" ".join(field.split()) for field in line.split(",")] for line in read_file(DICTIONARY)]
    index_of = {normalize(parts[0]): position for position, parts in enumerate(rows)}

    # base condition (no modality) and its variants, keyed by the stem
    bases: dict[str, int] = {}
    variants: dict[str, list[int]] = {}
    for position, parts in enumerate(rows):
        split = split_modality(parts[0])
        if split is None:
            bases.setdefault(normalize(parts[0]), position)
        else:
            variants.setdefault(split[0], []).append(position)

    merged: dict[int, list[str]] = {}
    drop: set[int] = set()
    collapsed: list[str] = []
    generalized: list[str] = []

    for stem, positions in sorted(variants.items()):
        base_position = bases.get(stem)
        if base_position is None and len(positions) < 2:
            if not args.generalize_single:
                continue
            base_position = -1
        members = [rows[position] for position in positions]
        keep_name = rows[base_position][0] if base_position is not None and base_position >= 0 else display_form(stem, members)

        terms: list[str] = [keep_name]
        seen = {normalize(keep_name)}
        ordered: list[int] = ([] if base_position is None or base_position < 0 else [base_position]) + positions
        for modality in MODALITY_ORDER:
            for position in positions:
                name = rows[position][0]
                split = split_modality(name)
                if split and split[1] == modality and normalize(name) not in seen:
                    seen.add(normalize(name))
                    terms.append(name)
        for position in ordered:
            for term in rows[position][1:]:
                if normalize(term) not in seen:
                    seen.add(normalize(term))
                    terms.append(term)

        target = base_position if base_position is not None and base_position >= 0 else positions[0]
        merged[target] = terms
        for position in ordered:
            if position != target:
                drop.add(position)
        label = f"  {keep_name!r} <- {[rows[position][0] for position in ordered]}  ({len(terms)} terms)"
        if base_position is None or base_position < 0:
            generalized.append(label)
        else:
            collapsed.append(label)

    kept = [merged.get(position, parts) for position, parts in enumerate(rows) if position not in drop]
    kept.sort(key=lambda parts: (normalize(parts[0]), parts[0]))

    print("families with an existing base condition:")
    for line in collapsed:
        print(line)
    if args.generalize_single:
        print("\nlone variants generalised (no base condition existed):")
        for line in generalized:
            print(line)

    print(f"\nfamilies collapsed : {len(collapsed)}")
    print(f"lone variants      : {len(generalized)}")
    print(f"lines removed      : {len(drop)}")
    print(f"lines: {len(rows)} -> {len(kept)}")

    if args.apply:
        DICTIONARY.write_text("\n".join(",".join(parts) for parts in kept) + "\n", encoding="utf-8")
        print(f"written: {DICTIONARY}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
