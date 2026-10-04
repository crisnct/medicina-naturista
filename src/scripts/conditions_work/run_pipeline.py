"""One-shot pipeline: rebuild data/medical_conditions.txt from the base dictionary.

Steps, in this order:
  1. merge every generated batch (deduplicating, folding synonyms into the owning
     condition, never copying a term into a second condition);
  2. collapse acute/chronic variants of one disease into a single line, keeping
     every synonym;
  3. attach Romanian folk synonyms, only when the folk name is still free, with a
     central owner list deciding contested names;
  4. repair the remaining cross-condition term collisions.

Run:  python run_pipeline.py [--skip-git]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[2]
sys.path.insert(0, str(WORK))
from merge_batches import BATCH_ORDER, DICTIONARY, normalize, read_file  # noqa: E402
from folk_overrides import OVERRIDES  # noqa: E402

PYTHON = sys.executable
# invariants the shipped dictionary must satisfy (mirrored in tests/unit/ai/test_conditions.py)
TARGET_COLUMNS = 7
_DIACRITICS = "ăâîșțşţĂÂÎȘȚŞŢ"
_DIACRITIC_MAX = 100


def run(title: str, script: str, *extra: str) -> None:
    print(f"\n===== {title} =====")
    result = subprocess.run([PYTHON, str(WORK / script), *extra], cwd=ROOT,
                            text=True, capture_output=True, encoding="utf-8", errors="replace")
    tail = [line for line in (result.stdout or "").splitlines() if line.strip()]
    for line in tail[-14:]:
        print(f"  {line}")
    if result.returncode != 0 and "collisions" not in (result.stdout or ""):
        print(f"  !! {script} exit {result.returncode}")
        for line in (result.stderr or "").splitlines()[-6:]:
            print(f"  {line}")


def merge_batches_inline() -> None:
    """Merge the batches and attach folk synonyms with a global owner check."""
    print("\n===== merge batches + folk synonyms =====")
    rows = [[" ".join(field.split()) for field in line.split(",")] for line in read_file(DICTIONARY)]
    index = {normalize(parts[0]): position for position, parts in enumerate(rows)}
    owner: dict[str, int] = {}
    for position, parts in enumerate(rows):
        for term in parts:
            owner.setdefault(normalize(term), position)

    # folk synonyms: central overrides decide contested names, chunks fill the rest.
    # several folk names per condition are kept, inserted right after the name.
    folk: dict[str, list[str]] = {}

    def remember_folk(name: str, value: str) -> None:
        key, term = normalize(name), " ".join(value.split())
        if not key or not term:
            return
        bucket = folk.setdefault(key, [])
        if normalize(term) not in {normalize(item) for item in bucket}:
            bucket.append(term)

    # folk names: the single approved source (the user's marked selection plus the
    # names approved in the earlier session), then the central owner decisions
    for path in sorted(WORK.glob("POP_clean.txt")):
        for line in read_file(path):
            name, _, value = line.partition("|")
            if name.strip() and value.strip():
                remember_folk(name, value)
    for disease, value in OVERRIDES:
        remember_folk(disease, value)

    # merge the chapter batches
    import merge_logic

    stats = merge_logic.merge(rows, index, owner)
    print(f"  batches merged          : {stats['added']} new conditions")
    print(f"  folded as duplicates    : {stats['folded']}")
    print(f"  dropped (other disease) : {stats['dropped']}")
    print(f"  structural problems     : {stats['problems']}")

    # attach folk synonyms only where the name is unclaimed. The index is rebuilt
    # from the current rows because merges change which row owns which term.
    attach_index: dict[str, int] = {}
    for position, parts in enumerate(rows):
        for term in parts:
            attach_index.setdefault(normalize(term), position)
    attached = 0
    conditions_with_folk = 0
    skipped: list[tuple[str, str, str]] = []
    for key, values in folk.items():
        position = index.get(key)
        if position is None:
            continue
        parts = rows[position]
        added_here = 0
        for value in values:
            value_key = normalize(value)
            holder = attach_index.get(value_key)
            if holder is not None and holder != position:
                skipped.append((parts[0], value, rows[holder][0]))
                continue
            if value_key in {normalize(term) for term in parts}:
                continue
            parts.insert(1 + added_here, value)
            attach_index[value_key] = position
            added_here += 1
            attached += 1
        if added_here:
            conditions_with_folk += 1
    print(f"  folk names attached     : {attached} (on {conditions_with_folk} conditions)")
    print(f"  folk names left to their existing owner: {len(skipped)}")
    for disease, value, holder in skipped[:10]:
        print(f"    {disease!r}: {value!r} already means {holder!r}")

    rows.sort(key=lambda parts: (normalize(parts[0]), parts[0]))
    DICTIONARY.write_text("\n".join(",".join(parts) for parts in rows) + "\n", encoding="utf-8")
    print(f"  written: {DICTIONARY} ({len(rows)} lines)")


def verify_invariants() -> int:
    """The same checks the unit tests run, so the pipeline cannot ship a bad file."""
    print("\n===== invariants =====")
    rows = [line.split(",") for line in read_file(DICTIONARY)]
    problems: list[str] = []
    names: dict[str, int] = {}
    terms: dict[str, int] = {}
    for number, fields in enumerate(rows, 1):
        if len(fields) < TARGET_COLUMNS:
            problems.append(f"line {number}: only {len(fields)} columns")
        if any(not field.strip() or field != field.strip() for field in fields):
            problems.append(f"line {number}: blank or padded field")
        if any(ch in _DIACRITICS for ch in ",".join(fields)):
            problems.append(f"line {number}: diacritics")
        key = normalize(fields[0])
        if key in names:
            problems.append(f"line {number}: duplicate condition {fields[0]!r} (line {names[key]})")
        names.setdefault(key, number)
        for field in fields:
            term = normalize(field)
            if term in terms and terms[term] != number:
                problems.append(f"line {number}: {field!r} also on line {terms[term]}")
            terms.setdefault(term, number)
    print(f"  conditions      : {len(rows)}")
    print(f"  unique terms    : {len(terms)}")
    print(f"  problems        : {len(problems)}")
    for problem in problems[:20]:
        print(f"    {problem}")
    return len(problems)


def split_merge_logic() -> None:
    """Keep merge_logic.py importable next to this script (no-op placeholder)."""
    return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-git", action="store_true", help="do not restore the base file first")
    args = parser.parse_args()

    if not args.skip_git:
        result = subprocess.run(["git", "checkout", "--", str(DICTIONARY)], cwd=ROOT,
                                text=True, capture_output=True)
        if result.returncode != 0:
            print(f"!! could not restore {DICTIONARY}: {result.stderr.strip()}")

    split_merge_logic()
    merge_batches_inline()
    run("collapse acute/chronic variants", "collapse_variants.py", "--apply")
    run("attach folk synonyms (overrides only)", "folk_overrides.py", "--apply")
    run("fix remaining collisions", "fix_collisions.py", "--apply")
    run("drop leftover shared terms", "cleanup_terms.py", "--apply")
    run("consolidate duplicate conditions", "consolidate_duplicates.py", "--apply")
    # short rows can only be detected after the removals above, so pad and merge last
    for _ in range(3):
        run("repair short rows", "repair_rows.py", "--apply")
        run("final targeted fixes", "final_fixes.py", "--apply")
    problems = verify_invariants()
    run("final validation", "check_conditions.py", "--quiet-report")
    print(f"\npipeline finished with {problems} invariant problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
