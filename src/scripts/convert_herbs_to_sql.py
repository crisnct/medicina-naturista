"""Validate and convert an explicitly supplied historical herb JSONL to SQL offline."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from psycopg import sql

from backend.ai.herb_validation import ALIASES, content_problems, convert_source
from backend.ai.herbs import Herb, parse_herbs


def read_source(path: Path) -> tuple[bytes, tuple[Herb, ...]]:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    problems = content_problems(text)
    if problems:
        raise ValueError("\n".join(problems))
    return raw, convert_source(parse_herbs(text))


def seed_sql(herbs: tuple[Herb, ...], source_hash: str) -> str:
    statements = [
        "-- Deterministic lowercase conversion; do not edit an applied migration.",
        f"-- Source SHA-256: {source_hash}",
        f"-- Species: {len(herbs)}; aliases: "
        + str(sum(len(getattr(h, key)) for h in herbs for key in ALIASES)),
    ]
    for herb in herbs:
        insert = sql.SQL(
            "INSERT INTO herbs (family, latin, ro, en) VALUES ({}) RETURNING id"
        ).format(
            sql.SQL(", ").join(
                sql.Literal(getattr(herb, key)) for key in ("family", "latin", "ro", "en")
            )
        )
        aliases = [(name, kind) for kind in ALIASES for name in getattr(herb, kind)]
        if aliases:
            values = sql.SQL(", ").join(
                sql.SQL("({}, {})").format(sql.Literal(name), sql.Literal(kind))
                for name, kind in aliases
            )
            statement = sql.SQL(
                "WITH plant AS ({}) INSERT INTO herb_aliases (herb_id, name, kind) "
                "SELECT plant.id, alias.name, alias.kind FROM plant CROSS JOIN "
                "(VALUES {}) AS alias(name, kind);"
            ).format(insert, values)
        else:
            statement = sql.SQL("{};").format(insert)
        statements.append(statement.as_string())
    return "\n".join(statements) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check and args.output is None:
        parser.error("--output is required unless --check is used")
    try:
        raw, herbs = read_source(args.source)
        digest = hashlib.sha256(raw).hexdigest()
        if not args.check:
            with args.output.open("x", encoding="utf-8", newline="\n") as target:
                target.write(seed_sql(herbs, digest))
    except (OSError, UnicodeError, ValueError) as error:
        raise SystemExit(str(error)) from None
    print(f"Validated {len(herbs)} species; source SHA-256: {digest}")


if __name__ == "__main__":
    main()
