#!/usr/bin/env python3
"""Measure retrieval quality and latency of ai/search.rank() against the
rule-labelled queries in tests/eval/retrieval_queries.json.

Metrics per query (chunk level, over rank()'s ordered output): Precision@10,
Reciprocal Rank of the first relevant chunk, nDCG@10 (binary gains) and
Recall@50 against ALL relevant chunks in the index. Latency is wall time of
one rank() call (the query embedding is warmed up first). It also counts
priority_order_violations: fragments with the named condition in their title
that rank below one without it (0 by construction of the score). Read-only: never
writes to the database. Run it before and after a scoring change and compare
the summaries (--output saves the full JSON for diffing).
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
import unicodedata
from pathlib import Path

from psycopg.rows import namedtuple_row

from medicina_naturista.ai import conditions, search
from medicina_naturista.ai.db import get_pool
from medicina_naturista.ai.search import rank

CASES_PATH = Path(__file__).resolve().parents[1] / "tests" / "eval" / "retrieval_queries.json"


# Case/diacritic-insensitive form used for every label comparison.
def plain(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in value if not unicodedata.combining(char))


def load_cases(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


# chunk_id -> (path, heading), both normalized, for every chunk in the index.
def load_chunk_index() -> dict[int, tuple[str, str]]:
    with get_pool().connection() as connection:
        with connection.cursor(row_factory=namedtuple_row) as cursor:
            rows = cursor.execute("SELECT chunk_id, source_relative_path, heading FROM chunks").fetchall()
    return {row.chunk_id: (plain(row.source_relative_path), plain(row.heading)) for row in rows}


def relevant_ids(case: dict, index: dict[int, tuple[str, str]]) -> set[int]:
    paths = [plain(item) for item in case.get("paths", [])]
    headings = [plain(item) for item in case.get("headings", [])]
    return {
        chunk_id for chunk_id, (path, heading) in index.items()
        if any(item in path for item in paths) or any(item in heading for item in headings)
    }


def ndcg_at(ranked: list[int], relevant: set[int], k: int) -> float:
    gains = [1.0 if chunk_id in relevant else 0.0 for chunk_id in ranked[:k]]
    dcg = sum(gain / math.log2(position + 2) for position, gain in enumerate(gains))
    ideal = sum(1.0 / math.log2(position + 2) for position in range(min(k, len(relevant))))
    return dcg / ideal if ideal else 0.0


def evaluate_case(case: dict, index: dict[int, tuple[str, str]]) -> dict:
    relevant = relevant_ids(case, index)
    started = time.perf_counter()
    results = rank(case["query"])
    latency_ms = (time.perf_counter() - started) * 1000
    ranked = [int(item["chunk_id"]) for item in results]
    named = conditions.resolve_query(case["query"]).condition_names
    first = next((position for position, chunk_id in enumerate(ranked, start=1) if chunk_id in relevant), None)
    return {
        "query": case["query"],
        "relevant_total": len(relevant),
        "candidates": len(ranked),
        "precision_at_10": sum(chunk_id in relevant for chunk_id in ranked[:10]) / 10,
        "reciprocal_rank": 1.0 / first if first else 0.0,
        "ndcg_at_10": ndcg_at(ranked, relevant, 10),
        "recall_at_50": (sum(chunk_id in relevant for chunk_id in ranked[:50]) / len(relevant)) if relevant else None,
        "latency_ms": latency_ms,
        "priority_order_violations": priority_order_violations(results) if named else 0,
    }


# Fragments with the named condition in their title (P1) must come before every
# other fragment: counts the P1 fragments that appear after a non-P1 one. Must
# be 0 by construction of the score (see the weights in ai/search.py).
def priority_order_violations(results: list[dict]) -> int:
    violations = 0
    seen_other = False
    for item in results:
        if item["condition_in_title"]:
            violations += seen_other
        else:
            seen_other = True
    return violations


def summarize(rows: list[dict]) -> dict:
    def mean(key: str) -> float:
        values = [row[key] for row in rows if row[key] is not None]
        return statistics.fmean(values) if values else 0.0

    latencies = sorted(row["latency_ms"] for row in rows)
    p95 = latencies[min(len(latencies) - 1, math.ceil(0.95 * len(latencies)) - 1)]
    return {
        "queries": len(rows),
        "precision_at_10": mean("precision_at_10"),
        "mrr": mean("reciprocal_rank"),
        "ndcg_at_10": mean("ndcg_at_10"),
        "recall_at_50": mean("recall_at_50"),
        "latency_p50_ms": statistics.median(latencies),
        "latency_p95_ms": p95,
        "priority_order_violations": sum(row.get("priority_order_violations", 0) for row in rows),
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=CASES_PATH)
    parser.add_argument("--no-conditions", action="store_true", help="do not recognise conditions (no P1/P2, no synonyms)")
    parser.add_argument("--output", type=Path, help="write the full per-query JSON here")
    args = parser.parse_args()

    cases = load_cases(args.cases)
    index = load_chunk_index()
    if args.no_conditions:
        search.resolve_query = conditions.ConditionDictionary([]).resolve
        conditions.resolve_query = search.resolve_query
    rank("warmup")  # load the embedding model outside the timed section
    rows = [evaluate_case(case, index) for case in cases]
    for row in rows:
        recall = "  n/a" if row["recall_at_50"] is None else f"{row['recall_at_50']:5.2f}"
        print(
            f"P@10={row['precision_at_10']:.1f} RR={row['reciprocal_rank']:.2f} "
            f"nDCG@10={row['ndcg_at_10']:.2f} R@50={recall} "
            f"rel={row['relevant_total']:4d} cand={row['candidates']:5d} "
            f"{row['latency_ms']:6.0f}ms  {row['query']}"
        )
    summary = summarize(rows)
    print(json.dumps(summary, indent=2))
    if args.output:
        args.output.write_text(
            json.dumps({"summary": summary, "queries": rows}, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
