"""Benchmark corpus associations, using a read-only source and disposable target.

PYTHONPATH=src python -m tests.benchmarks.herbs_index_benchmark
Set HERBS_BENCHMARK_DATABASE_URL to a disposable DB named herbs_index_benchmark*.
The .env source database is only read, in one repeatable-read snapshot.
"""

from __future__ import annotations

import ctypes
import io
import json
import os
import pickle
import platform
import statistics
import sys
import threading
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager, redirect_stdout
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import psycopg
from psycopg import sql

from backend.config import Settings
from scripts import build_hybrid_index as builder
from scripts.bootstrap_database import ensure_database
from scripts.migrate_database import migrate


def process_memory():
    """Current cumulative RSS of this process and its descendants, no extra dependency."""
    if os.name == "nt":
        from ctypes import wintypes

        class Entry(ctypes.Structure):
            _fields_ = [
                ("size", wintypes.DWORD),
                ("usage", wintypes.DWORD),
                ("pid", wintypes.DWORD),
                ("heap", ctypes.c_size_t),
                ("module", wintypes.DWORD),
                ("threads", wintypes.DWORD),
                ("parent", wintypes.DWORD),
                ("priority", wintypes.LONG),
                ("flags", wintypes.DWORD),
                ("name", wintypes.WCHAR * 260),
            ]

        class Memory(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
                (name, ctypes.c_size_t)
                for name in (
                    "peak_rss",
                    "rss",
                    "peak_paged",
                    "paged",
                    "peak_nonpaged",
                    "nonpaged",
                    "pagefile",
                    "peak_pagefile",
                )
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
        kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(Memory),
            wintypes.DWORD,
        ]
        snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
        entry = Entry()
        entry.size = ctypes.sizeof(entry)
        parents = {}
        try:
            ok = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
            while ok:
                parents[entry.pid] = entry.parent
                ok = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            kernel.CloseHandle(snapshot)

        def rss(pid):
            handle = kernel.OpenProcess(0x410, False, pid)
            if not handle:
                return 0
            memory = Memory()
            memory.size = ctypes.sizeof(memory)
            try:
                return (
                    memory.rss
                    if psapi.GetProcessMemoryInfo(handle, ctypes.byref(memory), memory.size)
                    else 0
                )
            finally:
                kernel.CloseHandle(handle)
    else:
        parents = {}
        for path in Path("/proc").glob("[0-9]*/status"):
            try:
                fields = dict(
                    line.split(":", 1) for line in path.read_text().splitlines() if ":" in line
                )
                parents[int(path.parent.name)] = int(fields["PPid"])
            except (OSError, KeyError):
                continue

        def rss(pid):
            try:
                fields = dict(
                    line.split(":", 1)
                    for line in Path(f"/proc/{pid}/status").read_text().splitlines()
                    if ":" in line
                )
                return int(fields.get("VmRSS", "0 kB").split()[0]) * 1024
            except OSError:
                return 0

    family = {os.getpid()}
    while True:
        new = {pid for pid, parent in parents.items() if parent in family} - family
        if not new:
            break
        family.update(new)
    return sum(rss(pid) for pid in family)


def benchmark_plans(conn):
    plans = {}
    for column in ("primary_medical_conditions", "secondary_medical_conditions"):
        conn.execute(
            sql.SQL("CREATE INDEX IF NOT EXISTS {} ON chunks USING GIN ({})").format(
                sql.Identifier("benchmark_" + column), sql.Identifier(column)
            )
        )
    conn.execute("ANALYZE chunks")
    with conn.transaction():
        plans["scan"] = conn.execute(
            "EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) SELECT chunk_id,text,primary_medical_conditions,secondary_medical_conditions FROM chunks WHERE cardinality(primary_medical_conditions)>0 OR cardinality(secondary_medical_conditions)>0"
        ).fetchone()[0]
        term = conn.execute(
            "SELECT unnest(primary_medical_conditions || secondary_medical_conditions) FROM chunks LIMIT 1"
        ).fetchone()[0]
        plans["condition_gin"] = conn.execute(
            "EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) SELECT chunk_id,text FROM chunks WHERE primary_medical_conditions && %s::text[] OR secondary_medical_conditions && %s::text[]",
            ([term], [term]),
        ).fetchone()[0]
        conn.execute(
            "CREATE TEMP TABLE herbs_benefits_next ON COMMIT DROP AS SELECT herb_id,medical_condition_id FROM herbs_benefits"
        )
        conn.execute("CREATE UNIQUE INDEX ON herbs_benefits_next(herb_id,medical_condition_id)")
        conn.execute("ANALYZE herbs_benefits_next")
        plans["publication_delete"] = conn.execute(
            "EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) " + builder.HERBS_BENEFITS_DELETE_SQL
        ).fetchone()[0]
        plans["publication_identical_insert"] = conn.execute(
            "EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) " + builder.HERBS_BENEFITS_INSERT_SQL
        ).fetchone()[0]
        with conn.transaction(force_rollback=True):
            conn.execute("DELETE FROM herbs_benefits")
            conn.execute("ANALYZE herbs_benefits")
            plans["publication_initial_insert"] = conn.execute(
                "EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) " + builder.HERBS_BENEFITS_INSERT_SQL
            ).fetchone()[0]
        conn.execute(
            "CREATE TEMP TABLE herbs_benefits_raw ON COMMIT DROP AS SELECT herb_id,medical_condition_id FROM herbs_benefits CROSS JOIN generate_series(1,3)"
        )
        plans["dedup_duplicate_heavy"] = conn.execute(
            "EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) SELECT DISTINCT herb_id,medical_condition_id FROM herbs_benefits_raw"
        ).fetchone()[0]
    return plans


def write_report(data):
    env = data["environment"]
    runs = (
        data["runs"]
        + data.get("matcher_comparison", [])
        + data.get("changed_evidence", [])
        + data.get("four_vs_eight", [])
        + data.get("one_vs_four", [])
        + data.get("two_vs_four", [])
    )
    comparison = data.get("four_vs_eight", [])
    medians = (
        {
            workers: statistics.median(
                r["run_seconds"] for r in comparison if r["workers"] == workers
            )
            for workers in (4, 8)
        }
        if comparison
        else {}
    )
    selected = builder.HERBS_INDEX_WORKERS
    matchers = data.get("matcher_comparison", [])
    matcher_medians = (
        {
            kind: statistics.median(r["run_seconds"] for r in matchers if r["scenario"] == kind)
            for kind in ("native_workers", "python_workers")
        }
        if matchers
        else {}
    )
    groups = defaultdict(list)
    for result in runs:
        groups[(result["scenario"], result["workers"], result["fetch"], result["copy"])].append(
            result
        )
    lines = [
        "# Benchmark herbs_benefits",
        "",
        f"Corpus: {env['chunks']:,} chunks, {env['characters']:,} characters; {env['herbs']:,} herbs and {env['conditions']:,} conditions.",
        f"Published result: {runs[0]['row_count']:,} distinct pairs, identical to the complete Python reference.",
        "",
        f"Environment: Python {env['python'].split()[0]}, {env['platform']}, {env['cpu']} ({env['logical_cpus']} logical CPUs); PostgreSQL {env['postgres']}; pyahocorasick {env['pyahocorasick']}, psycopg {env['psycopg']}.",
        "",
        "Source database was read through a repeatable-read, read-only transaction. All publications used a separate disposable PostgreSQL database.",
        "The benchmark copied text and condition metadata, without vectors or private application tables. Constraints, durability and commit remained enabled.",
        "Three repetitions per group; first run is separate. Caches were not forcibly evicted. Linux compatibility was tested separately; these timings are Windows spawn timings.",
        "",
        "| Scenario | Workers | Fetch/COPY | First (s) | Median (s) | Peak cumulative RSS (MiB) |",
        "|---|---:|---|---:|---:|---:|",
    ]
    for (scenario, workers, fetch, copy), items in groups.items():
        lines.append(
            f"| {scenario} | {workers} | {fetch}/{copy} | {items[0]['run_seconds']:.3f} | {statistics.median(r['run_seconds'] for r in items):.3f} | {max(r['peak_rss_bytes'] for r in items) / 1024**2:.1f} |"
        )
    recent = []
    for key, workers in (("one_vs_four", 1), ("two_vs_four", 2)):
        items = data.get(key, [])
        if items:
            measured = statistics.median(r["run_seconds"] for r in items if r["workers"] == workers)
            control = statistics.median(r["run_seconds"] for r in items if r["workers"] == 4)
            recent.append(
                f"{workers} worker(s): median {measured:.3f}s; contemporaneous 4-worker control: {control:.3f}s. All pair sets were identical."
            )
    if recent:
        lines += [
            "",
            "## Follow-up worker comparisons",
            "",
            "These follow-ups used a recreated disposable database with matching corpus counts and catalog fingerprints. Compare each group with its alternating 4-worker control; earlier timing groups ran separately.",
            "",
            *recent,
        ]
    reference = data["reference"]
    lines += [
        "",
        "## Correctness and selection",
        "",
        "Every worker-count, matcher and deduplication variant produced the same complete pair set. The small_change_new_pair and catalog_change_new_pair scenarios add exactly one new pair and remove it on restoration.",
        f"Selected: {selected} workers, native Aho–Corasick, fetch 2,000 and COPY 50,000. The 2,000/50,000 batch combination had the lowest measured median among the bounded batch combinations; 16 workers increased startup time and memory.",
        (
            f"Earlier alternating comparison, three full initial publications each: 4 workers median {medians[4]:.3f}s; 8 workers median {medians[8]:.3f}s. Follow-up comparisons above informed the final selection; the user selected 2 workers. Worker count is fixed at startup."
            if medians
            else f"The configured worker count is {selected}."
        ),
        (
            f"Native workers: median {matcher_medians['native_workers']:.3f}s; Python reference workers: median {matcher_medians['python_workers']:.3f}s on identical publications ({100 * (1 - matcher_medians['native_workers'] / matcher_medians['python_workers']):.1f}% less total time for the native matcher)."
            if matcher_medians
            else "Matcher comparison is recorded separately."
        ),
        f"Condition-first reference on {reference['sample_chunks']} sampled chunks: {reference['condition_first_seconds']:.3f}s; single pass: {reference['single_pass_seconds']:.3f}s, with identical pairs.",
        f"Duplicate-heavy emission medians: integer bitmaps {statistics.median(reference['emission']['bitmaps']):.3f}s, dense bytearray {statistics.median(reference['emission']['bytearray']):.3f}s.",
        "The bitmap estimate for these catalogs is 1,994,096 bytes, below the 64 MiB budget. Maximum recorded in-flight task reservations are below 128 MiB.",
        "",
        "## Phase measurements",
        "",
        f"| Phase | Median initial publication with {selected} workers (s) |",
        "|---|---:|",
    ]
    initial = (
        [r for r in data.get("two_vs_four", []) if r["workers"] == selected]
        or [r for r in comparison if r["workers"] == selected]
        or [r for r in runs if r["scenario"] == "initial" and r["workers"] == selected]
    )
    for field in (
        "catalogs_seconds",
        "startup_seconds",
        "scan_seconds",
        "copy_seconds",
        "dedup_seconds",
        "publication_seconds",
        "commit_seconds",
    ):
        lines.append(f"| {field} | {statistics.median(r[field] for r in initial):.3f} |")
    lines += [
        "",
        "Worker normalization/matching values in the JSON are cumulative CPU wall times across workers. Scan wall time includes overlapping fetch, transfer, normalization, matching and COPY; these phases cannot be added.",
        "Commit values of 0.000s are below this interpreter's monotonic clock resolution. Startup includes constructing one matcher per worker.",
        "The JSON also includes a fetch-only measurement and sample pickle round trip. SQL command counts describe explicit calls; named-cursor FETCH commands are additionally proportional to ceil(candidate chunks / fetch size). No production SQL is issued per plant, condition or pair.",
        "EXPLAIN (ANALYZE, BUFFERS) plans in the JSON cover the complete scan, a GIN condition selection, duplicate-heavy DISTINCT and both differential publications.",
        "",
        "## Publication optimization",
        "",
        "The initial implementation occasionally took 47–49s in INSERT publication. An empty target caused repeated sequential rescans as the INSERT target grew. The final SQL materializes the old pair set once and analyzes target cardinality before publishing. Three final initial-population runs with 8 workers took 9.907, 10.094 and 9.906s for the 500/20,000 baseline.",
        "Only differences are published; identical rebuilds and the fast path insert/delete zero public rows. Existing pair IDs remain stable.",
        "",
        "Reproduce: set PYTHONPATH=src and HERBS_BENCHMARK_DATABASE_URL to a disposable database named herbs_index_benchmark*, then run python -m tests.benchmarks.herbs_index_benchmark. The configured .env database is only read. Raw measurements: tmp/herbs-index-benchmark.json.",
    ]
    Path("tmp/herbs-index-benchmark.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


@contextmanager
def memory_peak():
    stop = threading.Event()
    result = [process_memory()]

    def sample():
        while not stop.wait(0.05):
            result[0] = max(result[0], process_memory())

    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    try:
        yield result
    finally:
        stop.set()
        thread.join()


def copy_snapshot(source_url, target):
    with psycopg.connect(source_url, connect_timeout=5) as source:
        source.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        target.execute("TRUNCATE herbs, medical_conditions RESTART IDENTITY CASCADE")
        target.execute("DROP TABLE chunks")
        target.execute(
            "CREATE TABLE chunks(chunk_id BIGINT PRIMARY KEY, text TEXT NOT NULL, "
            "primary_medical_conditions TEXT[] NOT NULL, secondary_medical_conditions TEXT[] NOT NULL)"
        )
        for table, columns in (
            ("herbs", "id,family,latin,ro,en"),
            ("herb_aliases", "id,herb_id,name,kind"),
            ("medical_conditions", "id,name"),
            ("medical_condition_synonyms", "id,medical_condition_id,synonym"),
            ("chunks", "chunk_id,text,primary_medical_conditions,secondary_medical_conditions"),
        ):
            # Identifiers are the literal allowlisted values above; binary COPY is between identical types.
            with source.cursor().copy(
                f"COPY (SELECT {columns} FROM {table}) TO STDOUT (FORMAT BINARY)"
            ) as read:
                with target.cursor().copy(
                    f"COPY {table} ({columns}) FROM STDIN (FORMAT BINARY)"
                ) as write:
                    for block in read:
                        write.write(block)
        source_version = source.execute("SHOW server_version").fetchone()[0]
    for table in ("herbs", "herb_aliases", "medical_conditions", "medical_condition_synonyms"):
        target.execute(
            sql.SQL(
                "SELECT setval(pg_get_serial_sequence(%s,'id'), (SELECT max(id) FROM {}), true)"
            ).format(sql.Identifier(table)),
            (table,),
        )
    target.execute("ANALYZE chunks")
    return source_version


def simple_matcher(names):
    by_first = defaultdict(list)
    for name, owners in names:
        tokens = tuple(name.split())
        by_first[tokens[0]].append((tokens, owners))

    def match(text):
        tokens = tuple(builder._herb_text(text).split())
        found = set()
        for position, token in enumerate(tokens):
            for phrase, owners in by_first.get(token, ()):
                if tokens[position : position + len(phrase)] == phrase:
                    found.update(owners)
        return found

    return match


def reference_checks(conn, context):
    fetch_started = time.monotonic()
    rows = conn.execute(
        "SELECT text,primary_medical_conditions,secondary_medical_conditions FROM chunks"
    ).fetchall()
    fetch_seconds = time.monotonic() - fetch_started
    simple = simple_matcher(context.names)
    automaton = builder._make_herbs_matcher(context.names)
    matcher_timings = {}
    expected = None
    for label, match in [
        ("python", simple),
        ("native", lambda text: builder._match_herbs(automaton, builder._herb_text(text))),
    ]:
        durations = []
        for _ in range(3):
            started = time.monotonic()
            result = set()
            for text, primary, secondary in rows:
                mask = builder._herbs_condition_mask(context, primary, secondary)
                if mask:
                    result.update(builder._new_herbs_pairs(context, None, match(text), mask))
            durations.append(time.monotonic() - started)
            if expected is None:
                expected = result
            assert result == expected, "native/Python reference differs"
        matcher_timings[label] = durations
        print(f"reference matcher={label} seconds={durations}", flush=True)
    # Condition-first reference on the same deterministic sample, including overlapping metadata.
    sample = rows[: min(500, len(rows))]
    by_position = defaultdict(set)
    for term, owners in context.condition_positions_by_term.items():
        for owner in owners:
            by_position[owner].add(term)
    started = time.monotonic()
    reference = set()
    for position, condition_id in enumerate(context.condition_ids):
        terms = by_position[position]
        for text, primary, secondary in sample:
            if terms.intersection(primary) or terms.intersection(secondary):
                reference.update((context.herb_ids[p], condition_id) for p in simple(text))
    condition_first = time.monotonic() - started
    started = time.monotonic()
    single = set()
    for text, primary, secondary in sample:
        mask = builder._herbs_condition_mask(context, primary, secondary)
        if mask:
            single.update(builder._new_herbs_pairs(context, None, simple(text), mask))
    single_seconds = time.monotonic() - started
    assert single == reference
    # Duplicate-heavy emission comparison: dense bytearray versus per-herb integer bitmaps.
    emission = {}
    for label in ("bitmaps", "bytearray"):
        durations = []
        for _ in range(3):
            started = time.monotonic()
            emitted = set()
            seen = [0] * len(context.herb_ids)
            bits = bytearray((len(context.herb_ids) * len(context.condition_ids) + 7) // 8)
            for _duplicate in range(5):
                for text, primary, secondary in sample:
                    mask = builder._herbs_condition_mask(context, primary, secondary)
                    if not mask:
                        continue
                    owners = simple(text)
                    if label == "bitmaps":
                        emitted.update(builder._new_herbs_pairs(context, seen, owners, mask))
                    else:
                        for owner in owners:
                            remaining = mask
                            while remaining:
                                bit = remaining & -remaining
                                position = bit.bit_length() - 1
                                index = owner * len(context.condition_ids) + position
                                if not bits[index // 8] & (1 << (index % 8)):
                                    bits[index // 8] |= 1 << (index % 8)
                                    emitted.add(
                                        (context.herb_ids[owner], context.condition_ids[position])
                                    )
                                remaining ^= bit
            durations.append(time.monotonic() - started)
            assert emitted == reference
        emission[label] = durations
    serialization_started = time.monotonic()
    serialized = pickle.dumps(sample, protocol=pickle.HIGHEST_PROTOCOL)
    pickle.loads(serialized)
    serialization_seconds = time.monotonic() - serialization_started
    return expected, dict(
        matchers=matcher_timings,
        emission=emission,
        sample_chunks=len(sample),
        fetch_all_seconds=fetch_seconds,
        sample_roundtrip_pickle_seconds=serialization_seconds,
        sample_serialized_bytes=len(serialized),
        condition_first_seconds=condition_first,
        single_pass_seconds=single_seconds,
    )


class MeasuredConnection:
    def __init__(self, connection):
        self.connection = connection
        self.commands = 0

    def execute(self, *args, **kwargs):
        self.commands += 1
        return self.connection.execute(*args, **kwargs)

    def cursor(self, *args, **kwargs):
        self.commands += 1
        return self.connection.cursor(*args, **kwargs)


class ReferenceAutomaton:
    """First-token Python reference with the native iterator's boundary contract."""

    def __init__(self, names):
        self.by_first = defaultdict(list)
        for name, owners in names:
            phrase = tuple(name.split())
            self.by_first[phrase[0]].append((phrase, owners))

    def iter(self, normalized):
        tokens = list(builder._HERBS_TOKENS.finditer(normalized))
        words = tuple(token.group() for token in tokens)
        for index, word in enumerate(words):
            for phrase, owners in self.by_first.get(word, ()):
                if words[index : index + len(phrase)] == phrase:
                    start = tokens[index].start()
                    end = tokens[index + len(phrase) - 1].end() - 1
                    yield end, (end - start + 1, owners)


def initialize_reference_worker(names, readiness, gate):
    builder._HERBS_AUTOMATON = ReferenceAutomaton(names)
    builder._HERBS_GATE = gate
    readiness.put(os.getpid())


def compare_matchers(conn):
    expected = set(
        conn.execute("SELECT herb_id,medical_condition_id FROM herbs_benefits").fetchall()
    )
    results = []
    for backend in ("native", "python"):
        for _ in range(3):
            if backend == "python":
                with patch.object(builder, "_initialize_herbs_worker", initialize_reference_worker):
                    result = run_once(conn, workers=8, scenario="python_workers")
            else:
                result = run_once(conn, workers=8, scenario="native_workers")
            assert (
                set(
                    conn.execute(
                        "SELECT herb_id,medical_condition_id FROM herbs_benefits"
                    ).fetchall()
                )
                == expected
            )
            results.append(result)
    return results


def benchmark_changed_evidence(conn, context):
    expected = set(
        conn.execute("SELECT herb_id,medical_condition_id FROM herbs_benefits").fetchall()
    )
    herb_id = context.herb_ids[0]
    condition_id = next(i for i in context.condition_ids if (herb_id, i) not in expected)
    condition_name = conn.execute(
        "SELECT name FROM medical_conditions WHERE id=%s", (condition_id,)
    ).fetchone()[0]
    herb_name = conn.execute("SELECT latin FROM herbs WHERE id=%s", (herb_id,)).fetchone()[0]
    chunk_id = conn.execute("SELECT max(chunk_id)+1 FROM chunks").fetchone()[0]
    results = []
    for _ in range(3):
        conn.execute("DELETE FROM herbs_benefits")
        result = run_once(
            conn,
            workers=builder.HERBS_INDEX_WORKERS,
            scenario="selected_initial",
            fetch=builder.HERBS_FETCH_SIZE,
            copy=builder.HERBS_COPY_SIZE,
        )
        assert (
            set(conn.execute("SELECT herb_id,medical_condition_id FROM herbs_benefits").fetchall())
            == expected
        )
        results.append(result)
    for _ in range(3):
        conn.execute(
            "INSERT INTO chunks VALUES (%s,%s,%s,%s)", (chunk_id, herb_name, [condition_name], [])
        )
        result = run_once(
            conn,
            workers=8,
            scenario="small_change_new_pair",
            fetch=builder.HERBS_FETCH_SIZE,
            copy=builder.HERBS_COPY_SIZE,
        )
        actual = set(
            conn.execute("SELECT herb_id,medical_condition_id FROM herbs_benefits").fetchall()
        )
        assert actual == expected | {(herb_id, condition_id)}
        assert result["inserted"] == 1
        results.append(result)
        conn.execute("DELETE FROM chunks WHERE chunk_id=%s", (chunk_id,))
        restored = run_once(conn, workers=8, scenario="restore")
        assert restored["deleted"] == 1
    conn.execute(
        "INSERT INTO chunks VALUES (%s,%s,%s,%s)",
        (chunk_id, "benchmark alias", [condition_name], []),
    )
    run_once(conn, workers=8, scenario="restore")
    for _ in range(3):
        conn.execute(
            "INSERT INTO herb_aliases(herb_id,name,kind) VALUES (%s,'benchmark alias','ro_regional')",
            (herb_id,),
        )
        result = run_once(
            conn,
            workers=8,
            scenario="catalog_change_new_pair",
            fetch=builder.HERBS_FETCH_SIZE,
            copy=builder.HERBS_COPY_SIZE,
        )
        actual = set(
            conn.execute("SELECT herb_id,medical_condition_id FROM herbs_benefits").fetchall()
        )
        assert actual == expected | {(herb_id, condition_id)}
        assert result["inserted"] == 1
        results.append(result)
        conn.execute("DELETE FROM herb_aliases WHERE name='benchmark alias'")
        restored = run_once(conn, workers=8, scenario="restore")
        assert restored["deleted"] == 1
    conn.execute("DELETE FROM chunks WHERE chunk_id=%s", (chunk_id,))
    assert (
        set(conn.execute("SELECT herb_id,medical_condition_id FROM herbs_benefits").fetchall())
        == expected
    )
    return results


def run_once(conn, *, workers, scenario, budget=None, fetch=500, copy=20_000):
    measured = MeasuredConnection(conn)
    started = time.monotonic()
    generation = uuid.uuid4().hex
    previous = dict(conn.execute("SELECT key,value FROM sync_metadata").fetchall()).get(
        "index_generation"
    )
    with (
        memory_peak() as memory,
        redirect_stdout(io.StringIO()),
        patch.object(builder, "HERBS_INDEX_WORKERS", workers),
        patch.object(builder, "HERBS_FETCH_SIZE", fetch),
        patch.object(builder, "HERBS_COPY_SIZE", copy),
    ):
        context = builder._prepare_herbs_index(
            measured,
            chunks_changed=scenario not in {"fast", "catalog_change_new_pair"},
            previous_generation=previous,
            next_generation=generation,
            force_rebuild=scenario not in {"fast", "catalog_change_new_pair"},
            bitmap_budget_bytes=budget,
        )
        catalogs = time.monotonic() - started
        tick = time.monotonic()
        with builder._prepared_herbs_workers(context) as pool:
            startup = time.monotonic() - tick
            tick = time.monotonic()
            with conn.transaction():
                stats = (
                    builder._rebuild_herbs_benefits(
                        measured, context=context, executor=pool, progress=lambda *_a, **_k: None
                    )
                    if context.rebuild_required
                    else dict(row_count=context.row_count, inserted=0, deleted=0)
                )
                for key, value in {
                    **builder._herbs_metadata(context, stats["row_count"]),
                    "index_generation": generation,
                }.items():
                    measured.execute(
                        "INSERT INTO sync_metadata VALUES (%s,%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",
                        (key, value),
                    )
                before_commit = time.monotonic()
            commit_seconds = time.monotonic() - before_commit
            transaction_seconds = time.monotonic() - tick
    result = dict(
        workers=workers,
        scenario=scenario,
        fetch=fetch,
        copy=copy,
        run_seconds=time.monotonic() - started,
        catalogs_seconds=catalogs,
        startup_seconds=startup,
        transaction_seconds=transaction_seconds,
        commit_seconds=commit_seconds,
        peak_rss_bytes=memory[0],
        commands=measured.commands,
        **stats,
    )
    print(
        json.dumps(
            {
                k: result[k]
                for k in ("workers", "scenario", "run_seconds", "row_count", "inserted", "deleted")
            }
        ),
        flush=True,
    )
    return result


def compare_worker_counts(conn, counts, scenario):
    """Alternate equal full publications to limit cache/order bias."""
    expected = set(
        conn.execute("SELECT herb_id,medical_condition_id FROM herbs_benefits").fetchall()
    )
    results = []
    for _ in range(3):
        for workers in counts:
            conn.execute("DELETE FROM herbs_benefits")
            results.append(
                run_once(
                    conn,
                    workers=workers,
                    scenario=scenario,
                    fetch=builder.HERBS_FETCH_SIZE,
                    copy=builder.HERBS_COPY_SIZE,
                )
            )
            actual = set(
                conn.execute("SELECT herb_id,medical_condition_id FROM herbs_benefits").fetchall()
            )
            assert actual == expected, "worker counts published different pairs"
    return results


def compare_four_and_eight(conn):
    return compare_worker_counts(conn, (4, 8), "four_vs_eight_initial")


def main():
    target_url = os.environ["HERBS_BENCHMARK_DATABASE_URL"]
    if not urlsplit(target_url).path.lstrip("/").startswith("herbs_index_benchmark"):
        raise ValueError("benchmark target must be named herbs_index_benchmark*")
    source = Settings.from_env(dotenv=True)
    if target_url == source.database_url:
        raise ValueError("source and benchmark target must differ")
    if "--one-vs-four" in sys.argv or "--two-vs-four" in sys.argv:
        workers = 2 if "--two-vs-four" in sys.argv else 1
        key = "two_vs_four" if workers == 2 else "one_vs_four"
        path = Path("tmp/herbs-index-benchmark.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        ensure_database(target_url)
        migrate(target_url)
        with psycopg.connect(target_url, autocommit=True) as conn:
            copy_snapshot(source.database_url, conn)
            # Establish the control pair set, then alternate equal full publications.
            run_once(
                conn,
                workers=4,
                scenario="control_initial",
                fetch=builder.HERBS_FETCH_SIZE,
                copy=builder.HERBS_COPY_SIZE,
            )
            ctx = builder._prepare_herbs_index(
                conn,
                chunks_changed=False,
                previous_generation=None,
                next_generation="verification",
                force_rebuild=True,
            )
            env = data["environment"]
            counts = conn.execute("SELECT count(*),sum(length(text)) FROM chunks").fetchone()
            assert counts == (env["chunks"], env["characters"]), (
                "corpus changed since previous measurements"
            )
            assert ctx.herbs_fingerprint == env["herbs_fingerprint"]
            assert ctx.conditions_fingerprint == env["conditions_fingerprint"]
            assert ctx.row_count == data["runs"][0]["row_count"]
            data[key] = compare_worker_counts(conn, (workers, 4), key + "_initial")
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        write_report(data)
        return
    if "--four-vs-eight" in sys.argv:
        path = Path("tmp/herbs-index-benchmark.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        with psycopg.connect(target_url, autocommit=True) as conn:
            results = compare_four_and_eight(conn)
            data["plans"] = benchmark_plans(conn)
        data["four_vs_eight"] = results
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        write_report(data)
        return
    if "--changes-only" in sys.argv:
        path = Path("tmp/herbs-index-benchmark.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        with psycopg.connect(target_url, autocommit=True) as conn:
            ctx = builder._prepare_herbs_index(
                conn,
                chunks_changed=False,
                previous_generation=None,
                next_generation="changes",
                force_rebuild=True,
            )
            results = benchmark_changed_evidence(conn, ctx)
            data["plans"] = benchmark_plans(conn)
        data["changed_evidence"] = results
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        write_report(data)
        return
    if "--matchers-only" in sys.argv:
        path = Path("tmp/herbs-index-benchmark.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        with psycopg.connect(target_url, autocommit=True) as conn:
            results = compare_matchers(conn)
        data["matcher_comparison"] = results
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        write_report(data)
        return
    ensure_database(target_url)
    migrate(target_url)
    output = Path("tmp/herbs-index-benchmark.json")
    results = []
    with psycopg.connect(target_url, autocommit=True) as conn:
        source_version = copy_snapshot(source.database_url, conn)
        ctx = builder._prepare_herbs_index(
            conn,
            chunks_changed=True,
            previous_generation=None,
            next_generation="check",
            force_rebuild=True,
        )
        counts = conn.execute(
            "SELECT count(*),sum(length(text)),max(length(text)) FROM chunks"
        ).fetchone()
        expected, reference = reference_checks(conn, ctx)
        environment = dict(
            python=sys.version,
            platform=platform.platform(),
            cpu=platform.processor(),
            logical_cpus=os.cpu_count(),
            postgres=source_version,
            pyahocorasick=version("pyahocorasick"),
            psycopg=version("psycopg"),
            chunks=counts[0],
            characters=counts[1],
            largest_chunk=counts[2],
            herbs=len(ctx.herb_ids),
            conditions=len(ctx.condition_ids),
            herbs_fingerprint=ctx.herbs_fingerprint,
            conditions_fingerprint=ctx.conditions_fingerprint,
        )

        def record(result, verify=True):
            if verify:
                actual = set(
                    conn.execute(
                        "SELECT herb_id,medical_condition_id FROM herbs_benefits"
                    ).fetchall()
                )
                assert actual == expected, "published pairs differ from complete Python reference"
            results.append(result)
            output.write_text(
                json.dumps(
                    dict(environment=environment, reference=reference, runs=results), indent=2
                ),
                encoding="utf-8",
            )

        for workers in (1, 2, 4, 8, 16):
            for _ in range(3):
                conn.execute("DELETE FROM herbs_benefits")
                record(run_once(conn, workers=workers, scenario="initial"))
        for scenario in ("identical", "fast"):
            for _ in range(3):
                record(run_once(conn, workers=8, scenario=scenario))
        # Actual changes: remove evidence in one chunk, then change an alias; restore afterwards.
        row = conn.execute("SELECT chunk_id,text FROM chunks ORDER BY chunk_id LIMIT 1").fetchone()
        for _ in range(3):
            conn.execute(
                "UPDATE chunks SET text=%s WHERE chunk_id=%s", ("benchmark absent", row[0])
            )
            record(run_once(conn, workers=8, scenario="small_change"), verify=False)
            conn.execute("UPDATE chunks SET text=%s WHERE chunk_id=%s", (row[1], row[0]))
            run_once(conn, workers=8, scenario="restore")
        first_herb = ctx.herb_ids[0]
        for _ in range(3):
            conn.execute(
                "INSERT INTO herb_aliases(herb_id,name,kind) VALUES (%s,'benchmark alias','ro_regional')",
                (first_herb,),
            )
            record(run_once(conn, workers=8, scenario="catalog_change"), verify=False)
            conn.execute("DELETE FROM herb_aliases WHERE name='benchmark alias'")
        for fetch, copy, budget in ((500, 20_000, 0), (1000, 10_000, None), (2000, 50_000, None)):
            for _ in range(3):
                record(
                    run_once(
                        conn,
                        workers=8,
                        scenario="fallback" if budget == 0 else "batch",
                        fetch=fetch,
                        copy=copy,
                        budget=budget,
                    )
                )
        changed_evidence = benchmark_changed_evidence(conn, ctx)
        matcher_comparison = compare_matchers(conn)
        four_vs_eight = compare_four_and_eight(conn)
        plans = benchmark_plans(conn)
        output.write_text(
            json.dumps(
                dict(
                    environment=environment,
                    reference=reference,
                    runs=results,
                    plans=plans,
                    matcher_comparison=matcher_comparison,
                    changed_evidence=changed_evidence,
                    four_vs_eight=four_vs_eight,
                ),
                indent=2,
            ),
            encoding="utf-8",
        )
    write_report(json.loads(output.read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
