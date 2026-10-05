"""Condition dictionaries for tests, written in the short comma-separated form
("Gripa,gripe\nFebra\n": the canonical name first, then its synonyms) and
turned into the JSON Lines of data/medical_conditions.jsonl."""
from __future__ import annotations

import json


def conditions_jsonl(rows: str) -> str:
    lines = []
    for row in rows.splitlines():
        if row.strip():
            name, *synonyms = row.split(",")
            lines.append(json.dumps({"name": name, "synonyms": synonyms}, ensure_ascii=False))
    return "\n".join(lines) + "\n"
