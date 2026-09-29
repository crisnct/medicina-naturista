#!/usr/bin/env python3
"""Rewrite Markdown source files in place, stripping external link
destinations and "Vezi și"/"vezi si" cross-references (see
medicina_naturista.ai.text_cleaning.clean_text).

Run this once (and again whenever new documents are added) before
rebuild_index.ps1: the hybrid index is built directly from already-clean
sources, so the indexer and Retriever never need to clean anything
themselves. clean_text() never removes a newline, so line numbers already
recorded for these files stay valid after the rewrite; and since a rewrite
changes each file's own bytes, the existing SHA-256-based incremental sync
picks up exactly the files this script touches on the next reindex — no
separate version bump is needed for the cleaning itself.

Only a file whose content actually changes is rewritten. A rewritten file's
line endings are normalized to bare "\\n" in the process (CRLF and lone CR
both become LF) — this changes the file's bytes but never its line count,
and matches how build_hybrid_index.py already normalizes line endings when
computing line numbers.
"""
from __future__ import annotations

import argparse
import codecs
import sys
from pathlib import Path

from medicina_naturista.ai.text_cleaning import clean_text

_FALLBACK_ENCODINGS = ("utf-8", "utf-16", "cp1250", "cp1252")


# Decode a Markdown file with the same encoding fallbacks build_hybrid_index.py
# uses, then normalize line endings to bare "\n" — writing raw bytes back out
# below skips Python's own text-mode newline translation, so this is the only
# place CRLF/CR get collapsed.
def _read(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    if raw.startswith(codecs.BOM_UTF8):
        decoded, encoding = raw.decode("utf-8-sig"), "utf-8-sig"
    else:
        decoded, encoding = None, None
        for candidate in _FALLBACK_ENCODINGS:
            try:
                decoded, encoding = raw.decode(candidate), candidate
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            decoded, encoding = raw.decode("utf-8", errors="replace"), "utf-8"
    normalized = decoded.replace("\r\n", "\n").replace("\r", "\n")
    return normalized, encoding


def clean_documents(source: Path, *, dry_run: bool) -> int:
    source = source.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Source directory does not exist: {source}")

    paths = sorted(
        (path for path in source.rglob("*.md") if path.is_file()),
        key=lambda item: item.relative_to(source).as_posix().casefold(),
    )
    changed = 0
    for path in paths:
        decoded, encoding = _read(path)
        cleaned = clean_text(decoded)
        if cleaned == decoded:
            continue
        changed += 1
        relative = path.relative_to(source).as_posix()
        print(f"{'Would clean' if dry_run else 'Cleaning'}: {relative}", flush=True)
        if not dry_run:
            # write_bytes(), not write_text(): the latter would re-apply
            # platform newline translation on top of the "\n"-only text
            # _read() already produced, corrupting line endings on Windows.
            path.write_bytes(cleaned.encode(encoding))

    verb = "Would rewrite" if dry_run else "Rewrote"
    print(f"{verb} {changed}/{len(paths)} files", flush=True)
    return changed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    project_root = Path(__file__).resolve().parents[1]
    parser.add_argument("--source", type=Path, default=project_root / "data" / "documents")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List files that would change without writing them",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    try:
        clean_documents(arguments.source, dry_run=arguments.dry_run)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
