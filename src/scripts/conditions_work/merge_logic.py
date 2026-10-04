"""Fold the generated batch files into the condition rows.

Rules (identical to merge_batches.py):
  * a row whose canonical name already exists is the same disease: its synonyms
    are folded into that line and the duplicate row disappears;
  * a row that shares a term with an existing condition folds into it when the two
    canonical names denote one disease; otherwise the row is dropped and counted;
  * no term is ever added to two different conditions.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

_TABLE = {ord(a): b for a, b in zip("ăâîșțşţĂÂÎȘȚŞŢ", "aaiststAAISTST")}
GENERIC = {
    "boala", "boli", "sindrom", "sindromul", "afectiune", "afectiuni", "tulburare",
    "tulburari", "acut", "acuta", "cronic", "cronica", "primar", "primara", "secundar",
    "secundara", "de", "la", "a", "al", "ale", "din", "cu", "si", "sau", "in", "pe",
    "pentru", "tip", "forma", "the", "of", "and", "with",
}
MIN_TERMS = 2
WORK = Path(__file__).resolve().parent
DICTIONARY = WORK.parents[2] / "data" / "medical_conditions.txt"

# A run may send every write to a scratch file: the pipeline exports this variable,
# the stage scripts pick it up, and only a fully verified file replaces the
# dictionary. Without the variable, writes go straight to DICTIONARY.
TARGET_ENV = "CONDITIONS_TARGET"


def target() -> Path:
    """The file the current run reads and writes."""
    import os

    override = os.environ.get(TARGET_ENV)
    return Path(override) if override else DICTIONARY

BATCH_ORDER = [
    "01_infectioase.txt", "02_neoplasme.txt", "03_sange_imun.txt",
    "04_endocrine_metabolice.txt", "05_psihice.txt", "06_nervos.txt",
    "07_ochi_ureche.txt", "08_circulator.txt", "09_respirator.txt",
    "10_digestiv.txt", "11_piele.txt", "12_osteoarticular.txt",
    "13_genitourinar.txt", "14_diverse.txt", "15_genetice.txt",
]


def normalize(value: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", value.translate(_TABLE).lower(), flags=re.UNICODE))


def core_tokens(value: str) -> frozenset[str]:
    return frozenset(word for word in normalize(value).split() if word not in GENERIC)


MODALITIES = {"acut", "acuta", "acute", "subacut", "subacuta", "subacute", "cronic",
              "cronica", "cronice", "chronic", "recurent", "recurenta", "recurrent",
              "recidivant", "recidivanta"}


def without_modality(name: str) -> str:
    tokens = normalize(name).split()
    while tokens and tokens[-1] in MODALITIES:
        tokens.pop()
    return " ".join(tokens)


def same_disease(left: str, right: str) -> bool:
    left_key, right_key = normalize(left), normalize(right)
    if left_key == right_key:
        return True
    # "Otita medie cronica" and "Otita medie" are one disease
    if without_modality(left) == without_modality(right):
        return True
    left_core, right_core = core_tokens(left), core_tokens(right)
    if not left_core or not right_core:
        return False
    if left_core == right_core or left_core < right_core or right_core < left_core:
        return True
    if len(left_core & right_core) / min(len(left_core), len(right_core)) >= 0.8:
        return True
    return SequenceMatcher(None, left_key, right_key).ratio() >= 0.75


def read_file(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def merge(rows: list[list[str]], index: dict[str, int], owner: dict[str, int]) -> dict[str, int]:
    added = folded = dropped = problems = 0
    for name in BATCH_ORDER:
        path = WORK / name
        if not path.exists():
            print(f"  .. missing batch: {name}")
            continue
        for text in read_file(path):
            terms = [" ".join(field.split()) for field in text.split(",")]
            if any(not term for term in terms) or len(terms) < MIN_TERMS:
                problems += 1
                continue
            keys = [normalize(term) for term in terms]
            if len(set(keys)) != len(keys):
                problems += 1
                continue

            target = index.get(keys[0])
            if target is not None:
                parts = rows[target]
                seen = {normalize(term) for term in parts}
                for term, key in zip(terms, keys):
                    if key not in seen:
                        seen.add(key)
                        parts.append(term)
                folded += 1
                continue

            clashes = {owner[key] for key in keys if key in owner}
            if clashes:
                matching = sorted(position for position in clashes
                                  if same_disease(terms[0], rows[position][0]))
                if matching:
                    target = matching[0]
                    foreign = {normalize(term) for position in clashes if position != target
                               for term in rows[position]}
                    parts = rows[target]
                    seen = {normalize(term) for term in parts}
                    for term, key in zip(terms, keys):
                        if (key == keys[0] or key not in foreign) and key not in seen:
                            seen.add(key)
                            parts.append(term)
                    folded += 1
                else:
                    dropped += 1
                continue

            position = len(rows)
            rows.append(terms)
            index.setdefault(keys[0], position)
            for key in keys:
                owner.setdefault(key, position)
            added += 1
    return {"added": added, "folded": folded, "dropped": dropped, "problems": problems}
