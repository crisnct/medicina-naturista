"""Review generated batches before merging: flag non-diseases and thin synonyms."""
from __future__ import annotations

import re
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]
DICTIONARY = ROOT / "data" / "medical_conditions.txt"
_TABLE = str.maketrans("ăâîșțşţĂÂÎȘȚŞŢ", "aaiststAAISTST")

# entries that are not diseases (procedures, physiological states, test names, bare symptoms)
NOT_A_DISEASE = re.compile(
    r"(?i)^(hemoroidectomie|apendicectomie|colecistectomie|dializa|chimioterapie|radioterapie|"
    r"vaccin|transplant|operatie|interventie|biopsie|endoscopie|colonoscopie|ecografie|"
    r"sarcina normala|nastere normala|alaptare|menopauza fiziologica|imunizare|"
    r"analiza|test |examen|scor |stadiu |clasificare)"
)
FILLER = re.compile(r"(?i)^(forma|tip|boala de tip|varianta|anemia de tip)\b")


def normalize(value: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", value.translate(_TABLE).lower(), flags=re.UNICODE))


def main() -> int:
    files = sorted(WORK.glob("[0-9][0-9]_*.txt"))
    if not files:
        print("no batch files found")
        return 0

    base_terms = set()
    for line in DICTIONARY.read_text(encoding="utf-8").splitlines():
        if line.strip():
            base_terms.update(normalize(field) for field in line.split(","))

    total = 0
    for path in files:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        total += len(lines)
        widths = {len(line.split(",")) for line in lines}
        print(f"\n=== {path.name}: {len(lines)} lines, column counts {sorted(widths)}")
        for number, line in enumerate(lines, 1):
            fields = [" ".join(f.split()) for f in line.split(",")]
            name = fields[0]
            if NOT_A_DISEASE.match(name):
                print(f"  [not-a-disease] {number}: {line[:100]}")
            if any(FILLER.match(field) for field in fields[1:4]):
                print(f"  [filler synonym] {number}: {line[:100]}")
            if len(name) > 70:
                print(f"  [long name] {number}: {name}")
            if len(fields) != 7:
                print(f"  [columns] {number}: {len(fields)} fields")
            if any(field.lower() == name.lower() for field in fields[1:4]):
                print(f"  [name repeated as synonym] {number}: {line[:100]}")
            # canonical names that read like a symptom rather than a disease
            if len(name.split()) <= 2 and normalize(name) not in base_terms:
                pass
    print(f"\ntotal generated lines: {total}")
    print(f"base terms: {len(base_terms)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
