"""Write the added folk names one per condition, flagging the doubtful ones.

Output format (one line per condition):
    NameBolii | popular1; popular2
Lines that start with "? " are the ones I would look at first: the folk name is
just a rephrasing of the canonical name, a plain description, or a very long
phrase rather than a name people actually use.

Run:  python list_added_folk.py [--all]
Writes: add_folk_review.txt   (flagged list)
        add_folk_clean.txt    (only the entries without a flag)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent
sys.path.insert(0, str(WORK))
from merge_logic import DICTIONARY, normalize, read_file  # noqa: E402
from folk_overrides import BLACKLIST, OVERRIDES  # noqa: E402

# words that make a phrase a description rather than a name
DESCRIPTION = re.compile(
    r"(?i)\b(la|in|de la|din|cu|pe|pentru|partea|zona|regiunea|mijlocul|aproape|langa|"
    r"dintre|foarte|prea|care|fara|cand|dupa|peste|sub)\b"
)
STOPWORDS = {"de", "la", "din", "cu", "pe", "in", "si", "sau", "a", "al", "ale", "un", "o"}


def content_words(value: str) -> set[str]:
    return {w for w in normalize(value).split() if w not in STOPWORDS}


def looks_weak(disease: str, folk: str) -> bool:
    """Only the clear cases: an echo of the canonical name, or a description."""
    disease_words, folk_words = content_words(disease), content_words(folk)
    if not folk_words:
        return True
    # the folk name is a strict subset of the condition's own words (nothing added)
    if folk_words < disease_words or folk_words == disease_words:
        return True
    # a whole phrase that only describes the symptom, not a name
    if len(folk.split()) >= 5:
        return True
    # the folk name just repeats one word of the canonical name
    if len(folk_words) == 1 and folk_words & disease_words:
        return True
    return False


def main() -> int:
    proposals: dict[str, list[str]] = {}
    for pattern in ("POP_[0-9].txt", "FOLK_[0-9][0-9].txt"):
        for path in sorted(WORK.glob(pattern)):
            for line in read_file(path):
                name, _, folk = line.partition("|")
                name, folk = " ".join(name.split()), " ".join(folk.split())
                if not name or not folk or normalize(folk) in BLACKLIST:
                    continue
                bucket = proposals.setdefault(name, [])
                if normalize(folk) not in {normalize(item) for item in bucket}:
                    bucket.append(folk)
    for disease, folk in OVERRIDES:
        bucket = proposals.setdefault(disease, [])
        if normalize(folk) not in {normalize(item) for item in bucket}:
            bucket.append(folk)

    owner: dict[str, str] = {}
    for line in read_file(DICTIONARY):
        parts = [" ".join(f.split()) for f in line.split(",")]
        for term in parts:
            owner.setdefault(normalize(term), parts[0])

    flagged: list[str] = []
    clean: list[str] = []
    for disease, values in sorted(proposals.items(), key=lambda item: normalize(item[0])):
        keep = [folk for folk in values if owner.get(normalize(folk)) == disease]
        if not keep:
            continue
        weak = [folk for folk in keep if looks_weak(disease, folk)]
        strong = [folk for folk in keep if folk not in weak]
        if weak:
            flagged.append(f"? {disease} | {'; '.join(keep)}")
        if strong:
            clean.append(f"{disease} | {'; '.join(strong)}")

    (WORK / "add_folk_review.txt").write_text("\n".join(flagged + clean) + "\n", encoding="utf-8")
    (WORK / "add_folk_clean.txt").write_text("\n".join(clean) + "\n", encoding="utf-8")

    total = len(flagged) + len(clean)
    print(f"conditions with a folk name : {total}")
    print(f"clean entries               : {len(clean)}  -> add_folk_clean.txt")
    print(f"entries worth a look (?)    : {len(flagged)}  -> marked at the top of add_folk_review.txt")
    print(f"\nwrote: {WORK / 'add_folk_review.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
