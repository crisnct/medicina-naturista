"""Drop entries that are injuries or isolated symptoms, not diseases.

Keeps the dictionary to diseases only, as requested by the user. Applied to the
generated batch files before merging.

Run:  python drop_non_diseases.py [--apply] [file ...]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent

# exact canonical names that are injuries / isolated symptoms / procedures / states
DROP: set[str] = {
    # injuries and trauma
    "plaga corneana", "plaga penetranta oculara", "arsura oculara termica",
    "arsura chimica oculara", "eroziune corneana", "hemoragie subconjunctivala",
    "hipema", "othematom", "corp strain auricular", "corpi straini oculari",
    "corp strain ocular", "hemoragie vitreana", "plaga", "rana",
    # isolated symptoms and signs
    "acuitate vizuala scazuta", "diplopie", "fotopsie", "metamorfopsie",
    "otalgie", "otoragie", "otoree", "epifora", "sindrom de ochi rosu",
    "sindrom de oboseala oculara digitala", "sindrom de ochi rosu",
    # procedures and apparatus
    "hemoroidectomie", "apendicectomie", "colecistectomie", "dializa",
    "chimioterapie", "radioterapie", "reanimare cardiopulmonara",
    "cerumen impactat",
}


def normalize(value: str) -> str:
    return value.strip().lower()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    files = args.files or sorted(WORK.glob("[0-9][0-9]_*.txt"))
    removed_total = 0
    for path in files:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        kept: list[str] = []
        for line in lines:
            name = line.split(",")[0].strip()
            if normalize(name) in DROP:
                print(f"  drop from {path.name}: {name}")
                removed_total += 1
                continue
            kept.append(line)
        if args.apply and len(kept) != len(lines):
            path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    print(f"removed: {removed_total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
