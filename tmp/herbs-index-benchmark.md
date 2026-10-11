# Benchmark herbs_benefits

Corpus: 10,777 chunks, 22,439,938 characters; 1,188 herbs and 6,284 conditions.
Published result: 105,837 distinct pairs, identical to the complete Python reference.

Environment: Python 3.11.0, Windows-10-10.0.26300-SP0, Intel64 Family 6 Model 183 Stepping 1, GenuineIntel (32 logical CPUs); PostgreSQL 16.15 (Debian 16.15-1.pgdg12+2); pyahocorasick 2.3.1, psycopg 3.3.6.

Source database was read through a repeatable-read, read-only transaction. All publications used a separate disposable PostgreSQL database.
The benchmark copied text and condition metadata, without vectors or private application tables. Constraints, durability and commit remained enabled.
Three repetitions per group; first run is separate. Caches were not forcibly evicted. Linux compatibility was tested separately; these timings are Windows spawn timings.

| Scenario | Workers | Fetch/COPY | First (s) | Median (s) | Peak cumulative RSS (MiB) |
|---|---:|---|---:|---:|---:|
| initial | 1 | 500/20000 | 7.172 | 7.203 | 213.8 |
| initial | 2 | 500/20000 | 6.687 | 6.000 | 272.3 |
| initial | 4 | 500/20000 | 7.485 | 7.485 | 396.1 |
| initial | 8 | 500/20000 | 9.907 | 9.907 | 640.6 |
| initial | 16 | 500/20000 | 16.797 | 16.094 | 1098.1 |
| identical | 8 | 500/20000 | 8.594 | 8.594 | 641.5 |
| fast | 8 | 500/20000 | 1.687 | 1.719 | 154.6 |
| small_change | 8 | 500/20000 | 8.500 | 8.562 | 648.3 |
| catalog_change | 8 | 500/20000 | 8.547 | 8.547 | 655.7 |
| fallback | 8 | 500/20000 | 9.391 | 9.546 | 663.9 |
| batch | 8 | 1000/10000 | 8.750 | 8.484 | 671.2 |
| batch | 8 | 2000/50000 | 8.438 | 8.422 | 686.2 |
| native_workers | 8 | 500/20000 | 8.734 | 8.484 | 699.6 |
| python_workers | 8 | 500/20000 | 9.797 | 9.828 | 736.0 |
| selected_initial | 8 | 2000/50000 | 8.687 | 9.954 | 622.2 |
| small_change_new_pair | 8 | 2000/50000 | 8.234 | 8.906 | 655.5 |
| catalog_change_new_pair | 8 | 2000/50000 | 9.141 | 8.391 | 665.6 |
| four_vs_eight_initial | 4 | 2000/50000 | 6.687 | 7.609 | 416.0 |
| four_vs_eight_initial | 8 | 2000/50000 | 10.515 | 10.515 | 645.6 |
| one_vs_four_initial | 1 | 2000/50000 | 5.437 | 5.594 | 244.8 |
| one_vs_four_initial | 4 | 2000/50000 | 5.578 | 5.656 | 418.2 |
| two_vs_four_initial | 2 | 2000/50000 | 5.047 | 5.031 | 307.0 |
| two_vs_four_initial | 4 | 2000/50000 | 5.766 | 5.766 | 425.8 |

## Follow-up worker comparisons

These follow-ups used a recreated disposable database with matching corpus counts and catalog fingerprints. Compare each group with its alternating 4-worker control; earlier timing groups ran separately.

1 worker(s): median 5.594s; contemporaneous 4-worker control: 5.656s. All pair sets were identical.
2 worker(s): median 5.031s; contemporaneous 4-worker control: 5.766s. All pair sets were identical.

## Correctness and selection

Every worker-count, matcher and deduplication variant produced the same complete pair set. The small_change_new_pair and catalog_change_new_pair scenarios add exactly one new pair and remove it on restoration.
Selected: 2 workers, native Aho–Corasick, fetch 2,000 and COPY 50,000. The 2,000/50,000 batch combination had the lowest measured median among the bounded batch combinations; 16 workers increased startup time and memory.
Earlier alternating comparison, three full initial publications each: 4 workers median 7.609s; 8 workers median 10.515s. Follow-up comparisons above informed the final selection; the user selected 2 workers. Worker count is fixed at startup.
Native workers: median 8.484s; Python reference workers: median 9.828s on identical publications (13.7% less total time for the native matcher).
Condition-first reference on 500 sampled chunks: 10.078s; single pass: 0.453s, with identical pairs.
Duplicate-heavy emission medians: integer bitmaps 1.843s, dense bytearray 2.172s.
The bitmap estimate for these catalogs is 1,994,096 bytes, below the 64 MiB budget. Maximum recorded in-flight task reservations are below 128 MiB.

## Phase measurements

| Phase | Median initial publication with 2 workers (s) |
|---|---:|
| catalogs_seconds | 0.485 |
| startup_seconds | 1.140 |
| scan_seconds | 1.391 |
| copy_seconds | 0.063 |
| dedup_seconds | 0.078 |
| publication_seconds | 1.875 |
| commit_seconds | 0.016 |

Worker normalization/matching values in the JSON are cumulative CPU wall times across workers. Scan wall time includes overlapping fetch, transfer, normalization, matching and COPY; these phases cannot be added.
Commit values of 0.000s are below this interpreter's monotonic clock resolution. Startup includes constructing one matcher per worker.
The JSON also includes a fetch-only measurement and sample pickle round trip. SQL command counts describe explicit calls; named-cursor FETCH commands are additionally proportional to ceil(candidate chunks / fetch size). No production SQL is issued per plant, condition or pair.
EXPLAIN (ANALYZE, BUFFERS) plans in the JSON cover the complete scan, a GIN condition selection, duplicate-heavy DISTINCT and both differential publications.

## Publication optimization

The initial implementation occasionally took 47–49s in INSERT publication. An empty target caused repeated sequential rescans as the INSERT target grew. The final SQL materializes the old pair set once and analyzes target cardinality before publishing. Three final initial-population runs with 8 workers took 9.907, 10.094 and 9.906s for the 500/20,000 baseline.
Only differences are published; identical rebuilds and the fast path insert/delete zero public rows. Existing pair IDs remain stable.

Reproduce: set PYTHONPATH=src and HERBS_BENCHMARK_DATABASE_URL to a disposable database named herbs_index_benchmark*, then run python -m tests.benchmarks.herbs_index_benchmark. The configured .env database is only read. Raw measurements: tmp/herbs-index-benchmark.json.
