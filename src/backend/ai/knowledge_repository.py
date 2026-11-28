"""Runs, cache, items, sources and atomic publication of the multilevel knowledge (migration 047).

One dedicated connection per build, holding KNOWLEDGE_LOCK for the whole process so two builds never
interleave. Every write is its own short transaction; a level becomes visible only when its run is
switched active, in one transaction, and the previous run stays active until then.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import psycopg
from psycopg.types.json import Jsonb

from backend.ai.index_state import INDEX_LOCK, IndexUnavailable, read_metadata
from backend.core.learning import KnowledgeRun

# Advisory lock of the knowledge builds; distinct from INDEX_LOCK and the migration lock.
KNOWLEDGE_LOCK = 7261040247
# Statuses a stopped or crashed full run can be resumed from.
RESUMABLE_STATUSES = ("running", "paused", "stopping", "failed")
# The columns run_from_row reads, in its order.
RUN_COLUMNS = (
    "run_id, language, level, model, prompt_sha256, status, is_active, units_total, units_done, "
    "published_utc, counters"
)

# Built once from constants: no value ever enters the statement text.
_ACTIVE_RUN_SQL = (
    "SELECT "
    + RUN_COLUMNS
    + " FROM knowledge_runs WHERE language = %s AND level = %s AND is_active"
)


def run_from_row(row: Sequence[Any]) -> KnowledgeRun:
    return KnowledgeRun(
        int(row[0]),
        str(row[1]),
        int(row[2]),
        str(row[3]),
        str(row[4]),
        str(row[5]),
        bool(row[6]),
        None if row[7] is None else int(row[7]),
        int(row[8]),
        row[9],
        dict(row[10]),
    )


@dataclass(frozen=True)
class Location:
    source_relative_path: str
    line_start: int
    line_end: int


@dataclass(frozen=True)
class Fragment:
    """One distinct fragment text of a language (L0), with every place it occurs in the index. The
    first occurrence's section path is the context the model sees."""

    text_sha256: str
    text: str
    heading: str
    locations: tuple[Location, ...]


@dataclass(frozen=True)
class IndexSnapshot:
    model_name: str
    model_dimension: int
    index_generation: str
    fragments: tuple[Fragment, ...]


@dataclass(frozen=True)
class NewItem:
    kind: str
    body: str
    subject_key: str | None
    attributes: dict[str, Any]
    input_sha256: str


@dataclass(frozen=True)
class Run:
    run_id: int
    status: str
    counters: dict[str, Any]


class KnowledgeRepository:
    def __init__(self, database_url: str) -> None:
        from pgvector.psycopg import register_vector

        self._connection = psycopg.connect(database_url, autocommit=True)
        register_vector(self._connection)

    def close(self) -> None:
        self._connection.close()

    # Session lock for the whole build; False when another build holds it.
    def try_lock(self) -> bool:
        row = self._connection.execute(
            "SELECT pg_try_advisory_lock(%s)", (KNOWLEDGE_LOCK,)
        ).fetchone()
        return bool(row and row[0])

    # The fragments of one language, read under the shared index lock so a running index sync is
    # refused (INDEX_MAINTENANCE) instead of read half-way.
    def index_snapshot(self, language: str) -> IndexSnapshot:
        with self._connection.transaction():
            row = self._connection.execute(
                "SELECT pg_try_advisory_xact_lock_shared(%s)", (INDEX_LOCK,)
            ).fetchone()
            if not (row and row[0]):
                raise IndexUnavailable()
            metadata = read_metadata(self._connection)
            rows = self._connection.execute(
                """
                SELECT text_sha256, text, heading, source_relative_path, line_start, line_end
                FROM chunks
                WHERE language = %s
                ORDER BY text_sha256, source_relative_path, line_start
                """,
                (language,),
            ).fetchall()
        fragments: list[Fragment] = []
        for text_sha256, text, heading, path, line_start, line_end in rows:
            location = Location(path, line_start, line_end)
            if fragments and fragments[-1].text_sha256 == text_sha256:
                last = fragments[-1]
                fragments[-1] = Fragment(
                    last.text_sha256, last.text, last.heading, (*last.locations, location)
                )
            else:
                fragments.append(Fragment(text_sha256, text, heading, (location,)))
        return IndexSnapshot(
            metadata.model_name,
            metadata.model_dimension,
            metadata.index_generation,
            tuple(fragments),
        )

    # Herbs (canonical Romanian name; Latin, English and alias names) and conditions (canonical name;
    # English name and synonyms), for linking claims to catalog keys.
    def catalog_names(
        self,
    ) -> tuple[list[tuple[str, list[str]]], list[tuple[str, list[str]]]]:
        herbs = self._connection.execute(
            """
            SELECT COALESCE(h.ro, h.latin, h.en),
                   array_remove(ARRAY[h.latin, h.en], NULL)
                   || COALESCE(array_agg(a.name) FILTER (WHERE a.name IS NOT NULL), ARRAY[]::text[])
            FROM herbs h LEFT JOIN herb_aliases a ON a.herb_id = h.id
            WHERE COALESCE(h.ro, h.latin, h.en) IS NOT NULL
            GROUP BY h.id
            """
        ).fetchall()
        conditions = self._connection.execute(
            """
            SELECT c.name,
                   array_remove(ARRAY[c.en], NULL)
                   || COALESCE(array_agg(s.synonym) FILTER (WHERE s.synonym IS NOT NULL),
                               ARRAY[]::text[])
            FROM medical_conditions c
            LEFT JOIN medical_condition_synonyms s ON s.medical_condition_id = c.id
            GROUP BY c.id
            """
        ).fetchall()
        return [(name, list(aliases)) for name, aliases in herbs], [
            (name, list(aliases)) for name, aliases in conditions
        ]

    # The latest stopped or crashed full run with the same model and prompt, to continue it.
    def resumable_run(self, language: str, level: int, model: str, prompt_sha: str) -> Run | None:
        row = self._connection.execute(
            """
            SELECT run_id, status, counters FROM knowledge_runs
            WHERE language = %s AND level = %s AND model = %s AND prompt_sha256 = %s
              AND status = ANY(%s) AND NOT counters ? 'sample'
            ORDER BY created_utc DESC LIMIT 1
            """,
            (language, level, model, prompt_sha, list(RESUMABLE_STATUSES)),
        ).fetchone()
        return Run(row[0], row[1], dict(row[2])) if row else None

    def active_run(self, language: str, level: int) -> KnowledgeRun | None:
        row = self._connection.execute(_ACTIVE_RUN_SQL, (language, level)).fetchone()
        return run_from_row(row) if row else None

    # Seconds per unit of the newest finished run of the level with this model, any language: where
    # the time-left estimate of a new run starts.
    def previous_speed(self, level: int, model: str) -> float | None:
        row = self._connection.execute(
            """
            SELECT (counters->>'seconds_per_unit')::float8 FROM knowledge_runs
            WHERE level = %s AND model = %s AND status = 'ready' AND counters ? 'seconds_per_unit'
            ORDER BY finished_utc DESC NULLS LAST LIMIT 1
            """,
            (level, model),
        ).fetchone()
        return float(row[0]) if row and row[0] and row[0] > 0 else None

    # Sample runs are review material only; a new sample replaces the previous ones.
    def delete_sample_runs(self, language: str, level: int) -> int:
        cursor = self._connection.execute(
            "DELETE FROM knowledge_runs WHERE language = %s AND level = %s AND counters ? 'sample'",
            (language, level),
        )
        return cursor.rowcount

    def create_run(
        self, language: str, level: int, model: str, prompt_sha: str, counters: dict[str, Any]
    ) -> int:
        row = self._connection.execute(
            """
            INSERT INTO knowledge_runs (language, level, model, prompt_sha256, status, counters)
            VALUES (%s, %s, %s, %s, 'queued', %s) RETURNING run_id
            """,
            (language, level, model, prompt_sha, Jsonb(counters)),
        ).fetchone()
        assert row is not None
        return int(row[0])

    def start_run(self, run_id: int, units_total: int, units_done: int) -> None:
        self._connection.execute(
            """
            UPDATE knowledge_runs
            SET status = 'running', started_utc = COALESCE(started_utc, now()), finished_utc = NULL,
                units_total = %s, units_done = %s
            WHERE run_id = %s
            """,
            (units_total, units_done, run_id),
        )

    def set_status(self, run_id: int, status: str, counters: dict[str, Any]) -> None:
        self._connection.execute(
            """
            UPDATE knowledge_runs
            SET status = %s, counters = %s,
                finished_utc = CASE WHEN %s IN ('ready', 'failed') AND started_utc IS NOT NULL
                                    THEN now() END
            WHERE run_id = %s
            """,
            (status, Jsonb(counters), status, run_id),
        )

    # Fragments that already have items in the run (a resumed run skips them).
    def fragments_with_items(self, run_id: int) -> set[str]:
        rows = self._connection.execute(
            """
            SELECT DISTINCT l.parent_text_sha256
            FROM knowledge_links l JOIN knowledge_items i ON i.item_id = l.child_item_id
            WHERE i.run_id = %s AND l.parent_text_sha256 IS NOT NULL
            """,
            (run_id,),
        ).fetchall()
        return {sha for (sha,) in rows}

    # A resumed run drops the items of fragments that left the index since it stopped.
    def delete_fragment_items(self, run_id: int, text_sha256s: Iterable[str]) -> int:
        cursor = self._connection.execute(
            """
            DELETE FROM knowledge_items i USING knowledge_links l
            WHERE i.run_id = %s AND l.child_item_id = i.item_id
              AND l.parent_text_sha256 = ANY(%s)
            """,
            (run_id, list(text_sha256s)),
        )
        return cursor.rowcount

    def cached_outputs(
        self, keys: Sequence[str], prompt_sha: str, model: str
    ) -> dict[str, dict[str, Any]]:
        rows = self._connection.execute(
            """
            SELECT input_sha256, output FROM knowledge_cache
            WHERE prompt_sha256 = %s AND model = %s AND input_sha256 = ANY(%s)
            """,
            (prompt_sha, model, list(keys)),
        ).fetchall()
        return {key: dict(output) for key, output in rows}

    def store_output(self, key: str, prompt_sha: str, model: str, output: dict[str, Any]) -> None:
        self._connection.execute(
            """
            INSERT INTO knowledge_cache (input_sha256, prompt_sha256, model, output)
            VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING
            """,
            (key, prompt_sha, model, Jsonb(output)),
        )

    # The items of one L1 fragment with their sources (every occurrence of the text) and their L0
    # parent, plus the run's progress, in one transaction: a crash never leaves half a fragment.
    def write_fragment(
        self,
        run_id: int,
        language: str,
        fragment: Fragment,
        items: Iterable[NewItem],
        units_done: int,
        counters: dict[str, Any],
    ) -> int:
        written = 0
        with self._connection.transaction():
            for item in items:
                row = self._connection.execute(
                    """
                    INSERT INTO knowledge_items (run_id, kind, subject_key, body, attributes,
                                                 input_sha256, source_count, ancestor_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 0) RETURNING item_id
                    """,
                    (
                        run_id,
                        item.kind,
                        item.subject_key,
                        item.body,
                        Jsonb(item.attributes),
                        item.input_sha256,
                        len(fragment.locations),
                    ),
                ).fetchone()
                assert row is not None
                item_id = row[0]
                with self._connection.cursor() as cursor:
                    cursor.executemany(
                        """
                        INSERT INTO knowledge_item_sources (item_id, language, text_sha256,
                            source_relative_path, line_start, line_end)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        [
                            (
                                item_id,
                                language,
                                fragment.text_sha256,
                                location.source_relative_path,
                                location.line_start,
                                location.line_end,
                            )
                            for location in fragment.locations
                        ],
                    )
                self._connection.execute(
                    "INSERT INTO knowledge_links (child_item_id, parent_text_sha256) VALUES (%s, %s)",
                    (item_id, fragment.text_sha256),
                )
                written += 1
            self.progress(run_id, units_done, counters)
        return written

    def progress(self, run_id: int, units_done: int, counters: dict[str, Any]) -> None:
        self._connection.execute(
            "UPDATE knowledge_runs SET units_done = %s, counters = %s WHERE run_id = %s",
            (units_done, Jsonb(counters), run_id),
        )

    # Embeddings of identical items (same input, kind and text) of the active run of the level,
    # when they have the index model's width; returns how many were copied.
    def reuse_embeddings(self, run_id: int, language: str, level: int, dimension: int) -> int:
        cursor = self._connection.execute(
            """
            UPDATE knowledge_items n SET embedding = o.embedding
            FROM knowledge_items o
            JOIN knowledge_runs r ON r.run_id = o.run_id
            WHERE n.run_id = %s AND n.embedding IS NULL
              AND r.is_active AND r.language = %s AND r.level = %s
              AND o.embedding IS NOT NULL AND vector_dims(o.embedding) = %s
              AND o.input_sha256 = n.input_sha256 AND o.kind = n.kind AND o.body = n.body
            """,
            (run_id, language, level, dimension),
        )
        return cursor.rowcount

    def items_without_embedding(self, run_id: int, limit: int) -> list[tuple[int, str]]:
        rows = self._connection.execute(
            """
            SELECT item_id, body FROM knowledge_items
            WHERE run_id = %s AND embedding IS NULL ORDER BY item_id LIMIT %s
            """,
            (run_id, limit),
        ).fetchall()
        return [(int(item_id), body) for item_id, body in rows]

    def store_embeddings(self, rows: Sequence[tuple[int, np.ndarray]]) -> None:
        with self._connection.transaction(), self._connection.cursor() as cursor:
            cursor.executemany(
                "UPDATE knowledge_items SET embedding = %s WHERE item_id = %s",
                [(vector, item_id) for item_id, vector in rows],
            )

    def item_counts(self, run_id: int) -> dict[str, int]:
        rows = self._connection.execute(
            "SELECT kind, count(*) FROM knowledge_items WHERE run_id = %s GROUP BY kind",
            (run_id,),
        ).fetchall()
        return {kind: int(count) for kind, count in rows}

    # Switch the active run of the language and level in one transaction. The run must be complete:
    # every unit done and every item embedded.
    def publish(self, run_id: int, language: str, level: int) -> None:
        with self._connection.transaction():
            row = self._connection.execute(
                """
                SELECT r.units_done = r.units_total,
                       NOT EXISTS (SELECT 1 FROM knowledge_items i
                                   WHERE i.run_id = r.run_id AND i.embedding IS NULL)
                FROM knowledge_runs r
                WHERE r.run_id = %s AND r.status = 'ready' AND NOT r.counters ? 'sample'
                FOR UPDATE
                """,
                (run_id,),
            ).fetchone()
            if row is None or not (row[0] and row[1]):
                raise RuntimeError("KNOWLEDGE_RUN_INCOMPLETE: the run is not ready to publish")
            self._connection.execute(
                """
                UPDATE knowledge_runs SET is_active = false
                WHERE language = %s AND level = %s AND is_active
                """,
                (language, level),
            )
            self._connection.execute(
                """
                UPDATE knowledge_runs SET is_active = true, published_utc = now()
                WHERE run_id = %s
                """,
                (run_id,),
            )
