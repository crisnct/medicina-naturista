#!/usr/bin/env python3
"""Dry run of the fragmentation (ai/fragmenter.py) over medicina-naturista-documente/data/documents: prints
how many fragments each business category gets and which are the largest,
without touching the database or computing any embedding. Run it before a full
reindex to see what the index will contain."""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

from backend.ai.conditions import load_dictionary
from backend.ai.fragmenter import BusinessCategory, fragment_document
from backend.config import settings

# Fragments longer than this are listed as "large" (no size limit applies to R1/R2).
LARGE_FRAGMENT_CHARS = 50_000


def _read(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1250", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    return text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")


def main() -> None:
    from backend.config import Settings, configure_settings
    configure_settings(Settings.from_env(dotenv=True))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=settings.documents_dir)
    parser.add_argument("--top", type=int, default=10, help="how many of the largest fragments to list")
    args = parser.parse_args()

    dictionary = load_dictionary()
    sizes: dict[BusinessCategory, list[int]] = {category: [] for category in BusinessCategory}
    largest: list[tuple[int, str, str, str]] = []
    documents = 0
    for path in sorted(args.source.rglob("*.md")):
        documents += 1
        relative = path.relative_to(args.source).as_posix()
        for fragment in fragment_document(_read(path), dictionary):
            sizes[fragment.business_category].append(len(fragment.text))
            largest.append((len(fragment.text), fragment.business_category.value, relative, fragment.path))

    print(f"{documents} documents, {sum(len(v) for v in sizes.values())} fragments")
    print(f"{'cat':<4}{'count':>8}{'chars':>14}{'median':>9}{'p95':>9}{'max':>11}{'>8000':>7}{f'>{LARGE_FRAGMENT_CHARS}':>8}")
    for category, values in sizes.items():
        if not values:
            print(f"{category.value:<4}{0:>8}")
            continue
        values.sort()
        print(
            f"{category.value:<4}{len(values):>8}{sum(values):>14,}{int(statistics.median(values)):>9,}"
            f"{values[max(0, int(len(values) * 0.95) - 1)]:>9,}{values[-1]:>11,}"
            f"{sum(v > 8000 for v in values):>7}{sum(v > LARGE_FRAGMENT_CHARS for v in values):>8}"
        )
    print(f"\nLargest {args.top} fragments:")
    for size, category, relative, heading in sorted(largest, reverse=True)[:args.top]:
        print(f"  {size:>10,}  {category}  {relative}  [{heading}]")


if __name__ == "__main__":
    main()
