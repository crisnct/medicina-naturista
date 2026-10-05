"""One-off: turn the RoDRG v1 tabular list (CIM-10-AM, Romanian) into tmp/icd10_work/icd10_ro.jsonl.

One code per line:
  {"code": "A41.0", "chapter": "I", "title_ro": "...", "inclusions": [...], "title_en": "..."}

`inclusions` are the plain inclusion terms printed under a code (alternative Romanian
names, e.g. "Febra de Oroya" under A44.0); Include/Exclude blocks are skipped.
`title_en` is the ICD-10-CM title of the same code, when the code exists there.

Run:  python src/scripts/icd10_work/extract_icd10.py
"""
from __future__ import annotations

import bisect
import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / "tmp" / "icd10_work"
PDF = WORK / "rodrg_v1_diagnostice.pdf"
CM_ORDER = WORK / "icd10cm" / "icd10cm_order_2026.txt"
OUT = WORK / "icd10_ro.jsonl"

# 0-based PDF pages of the tabular list from A00 to the end of chapter XVII (Q99)
FIRST_PAGE, LAST_PAGE = 51, 402

CHAPTERS = [
    ("I", "A00", "B99"), ("II", "C00", "D48"), ("III", "D50", "D89"), ("IV", "E00", "E90"),
    ("V", "F00", "F99"), ("VI", "G00", "G99"), ("VII", "H00", "H59"), ("VIII", "H60", "H95"),
    ("IX", "I00", "I99"), ("X", "J00", "J99"), ("XI", "K00", "K93"), ("XII", "L00", "L99"),
    ("XIII", "M00", "M99"), ("XIV", "N00", "N99"), ("XV", "O00", "O99"), ("XVI", "P00", "P96"),
    ("XVII", "Q00", "Q99"),
]

CODE_LINE = re.compile(r"^([A-Z]\d{2}(?:\.\d{1,2})?)(?:\s*[*†+]?)\s*(.*)$")
BLOCK_LINE = re.compile(r"^[A-Z]\d{2}\s*-\s*[A-Z]\d{2}\b")
PAGE_NUMBER = re.compile(r"^\d{1,4}$")
HEADER = re.compile(r"^Lista Tabelar")
STARTS_BLOCK = re.compile(r"^(Exclude|Include|Nota|Not[aă]|Utilizati|Folositi|Codificati)\b", re.I)
CONTINUES = ("-", ",", " de", " si", " cu", " a", " al", " ale", " in", " sau", " la", " din", " prin")


def chapter_of(code: str) -> str | None:
    head = code[:3]
    for name, first, last in CHAPTERS:
        if first <= head <= last:
            return name
    return None


def clean(text: str) -> str:
    # the PDF uses private-use glyphs for bullets
    text = "".join(" " if "" <= char <= "" else char for char in text)
    return " ".join(text.replace(" ", " ").split())


def sort_key(code: str) -> tuple[str, int, str]:
    return (code[0], int(code[1:3]), code[4:])


def sequence_lines(lines: list[str]) -> set[int]:
    """Indexes of the code lines that open real entries.

    Notes and Exclude lists also start lines with codes ("C02.8 ..."); those are
    cross-references. The real entries are the longest strictly increasing run of
    code lines through the document, so every line outside it is a reference.
    """
    candidates: list[tuple[int, tuple[str, int, str]]] = []
    for index, line in enumerate(lines):
        match = CODE_LINE.match(line)
        if not match or not chapter_of(match.group(1)):
            continue
        rest = match.group(2).strip()
        if rest and not (rest[:1].isupper() or rest[:1].isdigit()):
            continue
        candidates.append((index, sort_key(match.group(1))))
    # patience sorting with back-pointers
    tails: list[int] = []
    tail_keys: list[tuple[str, int, str]] = []
    back: list[int] = [-1] * len(candidates)
    for position, (_, key) in enumerate(candidates):
        slot = bisect.bisect_left(tail_keys, key)
        back[position] = tails[slot - 1] if slot else -1
        if slot == len(tails):
            tails.append(position)
            tail_keys.append(key)
        else:
            tails[slot] = position
            tail_keys[slot] = key
    chosen: set[int] = set()
    position = tails[-1] if tails else -1
    while position != -1:
        chosen.add(candidates[position][0])
        position = back[position]
    return chosen


def load_english() -> dict[str, str]:
    titles: dict[str, str] = {}
    for line in CM_ORDER.read_text(encoding="latin-1").splitlines():
        code = line[6:13].strip()
        if code:
            titles[code] = line[77:].strip()
    return titles


def page_lines(reader: PdfReader) -> list[str]:
    lines: list[str] = []
    for index in range(FIRST_PAGE, LAST_PAGE + 1):
        stripped = [clean(line) for line in (reader.pages[index].extract_text() or "").splitlines()]
        # every page starts with: chapter title, "Lista Tabelara a Bolilor RoDRG", page number
        body_start = 0
        for position, line in enumerate(stripped[:6]):
            if HEADER.match(line):
                body_start = position + 1
                if body_start < len(stripped) and PAGE_NUMBER.match(stripped[body_start]):
                    body_start += 1
                break
        lines.extend(stripped[body_start:])
        lines.append("")
    return lines


def parse(lines: list[str]) -> list[dict]:
    entries: list[dict] = []
    current: dict | None = None
    mode = "none"          # title | inclusions | skip
    pending = False        # code printed on its own line, title still to come
    real = sequence_lines(lines)
    for index, line in enumerate(lines):
        if not line:
            if mode == "skip":
                mode = "inclusions" if current else "none"
            continue
        if BLOCK_LINE.match(line):
            mode = "skip"
            continue
        match = CODE_LINE.match(line)
        if match and chapter_of(match.group(1)):
            code, rest = match.group(1), match.group(2).strip()
            # a bare number after the code is a stray page/column artefact
            rest = "" if re.fullmatch(r"\d+", rest) else rest
            if index in real:
                current = {"code": code, "title_ro": rest, "inclusions": []}
                entries.append(current)
                pending = not rest
                mode = "title"
                continue
            mode = "skip"
            continue
        if current is None or PAGE_NUMBER.match(line):
            continue
        if pending:
            if STARTS_BLOCK.match(line) or not line[:1].isupper():
                continue
            current["title_ro"] = line
            pending = False
            continue
        if STARTS_BLOCK.match(line):
            mode = "skip"
            continue
        if mode == "skip":
            continue
        if line.startswith(("-", "•", "*")) or line.endswith(":"):
            if line.endswith(":"):
                mode = "skip"
            continue
        in_inclusions = mode == "inclusions" and bool(current["inclusions"])
        previous = current["inclusions"][-1] if in_inclusions else current["title_ro"]
        if previous.endswith(CONTINUES) or line[:1].islower() or line[:1] in "[(":
            if previous.endswith("-") and not previous.endswith(" -"):
                joined = previous + line
            else:
                joined = f"{previous} {line}"
            if in_inclusions:
                current["inclusions"][-1] = joined
            else:
                current["title_ro"] = joined
            continue
        mode = "inclusions"
        current["inclusions"].append(line)
    return entries


def main() -> int:
    reader = PdfReader(str(PDF))
    entries = parse(page_lines(reader))
    english = load_english()
    with OUT.open("w", encoding="utf-8", newline="\n") as handle:
        for entry in entries:
            row = {
                "code": entry["code"],
                "chapter": chapter_of(entry["code"]),
                "title_ro": clean(entry["title_ro"]).replace("datorit ", "datorita "),
                "inclusions": [item for item in (clean(text) for text in entry["inclusions"]) if item != "NOS"],
                "title_en": english.get(entry["code"].replace(".", ""), ""),
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    codes = [entry["code"] for entry in entries]
    three = [code for code in codes if len(code) == 3]
    print(f"codes: {len(codes)}  three-character: {len(three)}")
    print(f"without ICD-10-CM title: {sum(1 for code in codes if code.replace('.', '') not in english)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
