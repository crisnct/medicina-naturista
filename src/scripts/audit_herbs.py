#!/usr/bin/env python3
"""Read-only audit of data/herbs.jsonl, written as a Markdown report to
tmp/herbs_review.md: totals, species without a Romanian or an English name,
Romanian names shared by several species, Latin names changed to the accepted
one. When the working files of the catalogue's construction are still there
(tmp/herbs_candidates.jsonl, tmp/herbs_work/herbs_provenance.jsonl), the report
also gives each species' group, origin, sources and where its regional names
came from."""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from backend.ai.conditions import _normalize  # noqa: E402
from backend.ai.herbs import parse_herbs  # noqa: E402

HERBS = ROOT / "data" / "herbs.jsonl"
REVIEW = ROOT / "tmp" / "herbs_candidates.jsonl"
PROVENANCE = ROOT / "tmp" / "herbs_work" / "herbs_provenance.jsonl"
TARGET = ROOT / "tmp" / "herbs_review.md"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    herbs = parse_herbs(HERBS.read_text(encoding="utf-8"))
    review = {row["latin"]: row for row in read_jsonl(REVIEW)}
    provenance = {row["latin"]: row for row in read_jsonl(PROVENANCE)}
    # the review list names a species by the name it had then: map renamed ones back
    for row in provenance.values():
        for old in [*row.get("review_names", []), *row.get("renamed_from", []), *row.get("merged", [])]:
            if old in review and row["latin"] not in review:
                review[row["latin"]] = review[old]
    out: list[str] = ["# Raport de verificare: data/herbs.jsonl", ""]

    out += ["## Totaluri", "", f"- specii: **{len(herbs)}**"]
    if review:
        groups = collections.Counter(review.get(h.latin, {}).get("group", "?") for h in herbs)
        origins = collections.Counter(review.get(h.latin, {}).get("origin", "?") for h in herbs)
        out.append("- pe grup: " + ", ".join(f"{name} {count}" for name, count in groups.most_common()))
        out.append("- pe origine: " + ", ".join(f"{name} {count}" for name, count in origins.most_common()))
    if provenance:
        sources = collections.Counter(source.split(":")[0] for row in provenance.values() for source in row["sources"])
        out.append("- pe sursa (o specie poate avea mai multe): " + ", ".join(f"{name} {count}" for name, count in sources.most_common()))
    out += [f"- fara nume romanesc (`ro` = numele latin): **{sum(h.ro == h.latin for h in herbs)}**",
            f"- fara nume englezesc (`en` gol): **{sum(not h.en for h in herbs)}**",
            f"- cu denumiri regionale: {sum(bool(h.ro_regional) for h in herbs)} "
            f"({sum(len(h.ro_regional) for h in herbs)} denumiri)",
            f"- cu sinonime latine: {sum(bool(h.latin_synonyms) for h in herbs)}", ""]

    if provenance:
        renamed = [(h.latin, row["renamed_from"]) for h in herbs if (row := provenance.get(h.latin)) and row.get("renamed_from")]
        merged = [(h.latin, row["merged"]) for h in herbs if (row := provenance.get(h.latin)) and row.get("merged")]
        out += ["## Nume latine schimbate in numele acceptat", ""]
        out += [f"- {', '.join(old)} -> *{new}*" for new, old in renamed] or ["- niciunul"]
        out += ["", "## Dubluri unite", ""]
        out += [f"- *{new}* <- {', '.join(old)}" for new, old in merged] or ["- niciuna"]
        regional_origins = collections.Counter(origin for row in provenance.values() for origin in row["ro_regional_from"].values())
        out += ["", "## De unde vin denumirile regionale", "",
                "- " + ", ".join(f"{name}: {count}" for name, count in regional_origins.most_common()),
                "- `corpus` = numele scris langa numele latin in documentele romanesti, gasit de cel putin doua ori; "
                "`dictionar` = \"Dictionarul plantelor de leac\"; `GBIF` = numele romanesti din GBIF; "
                "`unire de dubluri` = numele romanesc al intrarii unite.", ""]

    shared_ro: dict[str, list[str]] = collections.defaultdict(list)
    for herb in herbs:
        if herb.ro != herb.latin:
            shared_ro[_normalize(herb.ro)].append(herb.latin)
    out += ["## Acelasi `ro` la mai multe specii", ""]
    out += [f"- **{key}**: {', '.join(f'*{latin}*' for latin in latins)}"
            for key, latins in sorted(shared_ro.items()) if len(latins) > 1] or ["- niciunul"]

    shared_regional: dict[str, list[str]] = collections.defaultdict(list)
    for herb in herbs:
        for name in herb.ro_regional:
            shared_regional[_normalize(name)].append(herb.latin)
    out += ["", "## Denumiri regionale comune mai multor specii", ""]
    out += [f"- **{key}**: {', '.join(f'*{latin}*' for latin in latins)}"
            for key, latins in sorted(shared_regional.items()) if len(latins) > 1] or ["- niciuna"]

    out += ["", "## Specii fara nume romanesc (`ro` = numele latin)", ""]
    out += [f"- *{h.latin}*" + (f" ({h.en})" if h.en else "") for h in herbs if h.ro == h.latin] or ["- niciuna"]
    out += ["", "## Specii fara nume englezesc uzual (`en` gol)", ""]
    out += [f"- *{h.latin}* ({h.ro})" for h in herbs if not h.en] or ["- niciuna"]

    out += ["", "## Toate speciile", "", "| ro | latin | grup | origine | surse | regionale (sursa) |", "|---|---|---|---|---|---|"]
    for herb in herbs:
        row = review.get(herb.latin, {})
        prov = provenance.get(herb.latin, {})
        regional = "; ".join(f"{name} ({prov.get('ro_regional_from', {}).get(name, '?')})" for name in herb.ro_regional)
        out.append(f"| {herb.ro} | *{herb.latin}* | {row.get('group', '')} | {row.get('origin', '')} | "
                   f"{', '.join(prov.get('sources', []))} | {regional} |")

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"{len(herbs)} species -> {TARGET}")


if __name__ == "__main__":
    main()
