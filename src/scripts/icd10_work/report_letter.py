"""One-off: step P8 of the ICD-10 plan — write tmp/icd10_work/report_<L>.md.

Combines candidates_<L>.jsonl (match_letter.py), add_<L>.jsonl (the lines
inserted) and notes_<L>.md (the manual decisions, optional).

Run:  python src/scripts/icd10_work/report_letter.py A
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / "tmp" / "icd10_work"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    letter = sys.argv[1].upper()
    candidates = read_jsonl(WORK / f"candidates_{letter}.jsonl")
    added = read_jsonl(WORK / f"add_{letter}.jsonl")
    notes = WORK / f"notes_{letter}.md"
    covered = {code for row in added for code in row.get("codes", [])}
    verdicts = Counter(row["verdict"] for row in candidates)
    reasons = Counter(row.get("reason") for row in candidates if row["verdict"] == "eliminat")

    out: list[str] = [f"# Litera {letter} — raport CIM-10", ""]
    out.append(f"- coduri CIM-10 cu titlul la litera {letter}: **{len(candidates)}**")
    out.append(f"- eliminate automat (P2): **{verdicts['eliminat']}**")
    for reason, count in reasons.most_common():
        out.append(f"  - {reason}: {count}")
    out.append(f"- găsite automat în dicționar (P4.1–P4.3): **{verdicts['exista']}**")
    out.append(f"- de decis manual (`nou` + `posibil`): **{verdicts['nou'] + verdicts['posibil']}**")
    out.append(f"- **afecțiuni adăugate: {len(added)}**")
    out.append("")
    if notes.exists():
        out += ["## Decizii manuale", "", notes.read_text(encoding="utf-8").strip(), ""]
    out += ["## Adăugate", "", "| Nume canonic | Coduri | Sinonime |", "|---|---|---|"]
    for row in sorted(added, key=lambda item: item["name"].lower()):
        out.append(f"| {row['name']} | {', '.join(row.get('codes', []))} | {'; '.join(row['synonyms'])} |")
    out += ["", "## Decise manual, neadăugate", "",
            "Titluri `nou` / `posibil` care nu au devenit afecțiuni noi: există sub alt nume, sunt variante ale "
            "unei categorii (D5), categorii generice sau nu sunt boli (G7). Coloana „Apropiat” e sugestia automată.", "",
            "| Cod | Titlu CIM-10 | Apropiat |", "|---|---|---|"]
    for row in candidates:
        if row["verdict"] in ("nou", "posibil") and row["code"] not in covered:
            out.append(f"| {row['code']} | {row['title_ro']} | {' / '.join(row.get('similar', []))} |")
    out += ["", "## Existente (potrivire automată)", "",
            "Candidații pentru sinonime adăugate ulterior (D6).", "",
            "| Cod | Titlu CIM-10 | Afecțiune | Potrivire |", "|---|---|---|---|"]
    for row in candidates:
        if row["verdict"] == "exista":
            out.append(f"| {row['code']} | {row['title_ro']} | {row['condition']} | {row['level']} |")
    (WORK / f"report_{letter}.md").write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    print(f"report_{letter}.md: {len(added)} added, {verdicts['nou'] + verdicts['posibil'] - len(covered & {r['code'] for r in candidates})} manual not added")
    return 0


if __name__ == "__main__":
    sys.exit(main())
