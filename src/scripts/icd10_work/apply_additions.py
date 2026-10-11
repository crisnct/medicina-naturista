"""Validate ICD additions against PostgreSQL and generate a new SQL migration."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from backend.ai.conditions import _normalize, load_dictionary, make_condition  # noqa: E402
from backend.config import Settings, configure_settings  # noqa: E402
from scripts.condition_sql import additions_sql  # noqa: E402

WORK = ROOT / "tmp" / "icd10_work"
MIGRATIONS = ROOT / "src" / "backend" / "migrations"


def sort_key(name: str) -> tuple[str, str]:
    return (_normalize(name), name)


def problems_of(rows: list[dict], existing: list[dict]) -> list[str]:
    owner: dict[str, str] = {}
    for record in existing:
        for term in [record["name"], *record["synonyms"]]:
            owner.setdefault(_normalize(term), record["name"])
    problems: list[str] = []
    for row in rows:
        name = row["name"]
        terms = [name, *row["synonyms"]]
        if len(row["synonyms"]) < 6:
            problems.append(f"{name}: only {len(row['synonyms'])} synonyms")
        keys = [_normalize(term) for term in terms]
        if len(set(keys)) != len(keys):
            problems.append(f"{name}: duplicate terms in the line {[t for t, k in zip(terms, keys) if keys.count(k) > 1]}")
        for term, key in zip(terms, keys):
            if not term.isascii():
                problems.append(f"{name}: non-ASCII term {term!r}")
            if "," in term or term != " ".join(term.split()) or not term:
                problems.append(f"{name}: malformed term {term!r}")
            if len(term) > 70:
                problems.append(f"{name}: term too long {term!r}")
            if key in owner and owner[key] != name:
                problems.append(f"{name}: term {term!r} already belongs to {owner[key]!r}")
        for key in keys:
            owner.setdefault(key, name)
    return problems


def main() -> int:
    configure_settings(Settings.from_env(dotenv=True))
    letter = sys.argv[1].upper()
    check_only = "--check" in sys.argv
    source = WORK / f"add_{letter}.jsonl"
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    existing = [{"name": c.name, "synonyms": list(c.terms[1:])} for c in load_dictionary().conditions]

    problems = problems_of(rows, existing)
    if problems:
        print("\n".join(problems))
        print(f"{len(problems)} problem(s); nothing written")
        return 1
    if check_only:
        print(f"{letter}: {len(rows)} new conditions pass every check")
        return 0

    next_version = max(int(path.name.split("_", 1)[0]) for path in MIGRATIONS.glob("*.sql")) + 1
    target = MIGRATIONS / f"{next_version:03d}_add_conditions_{letter.lower()}.sql"
    ordered = sorted(rows, key=lambda row: sort_key(row["name"]))
    seed = additions_sql([make_condition(row["name"], row["synonyms"]) for row in ordered])
    with target.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(seed)
    print(f"{letter}: generated {target.name} with {len(rows)} additions; apply through reindexing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
