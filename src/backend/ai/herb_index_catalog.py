"""Catalog matching and fingerprints shared by association indexing and reading."""

from __future__ import annotations

import hashlib
import json
import re
from types import MappingProxyType

from backend.ai.condition_repository import CatalogUnavailable
from backend.ai.conditions import _normalize
from backend.ai.herb_repository import HERBS_INDEX_VERSION, HerbCatalogUnavailable
from backend.ai.herb_validation import catalog_problems
from backend.ai.herbs import Herb
from backend.ai.query_terms import plain

HERB_TOKENS = re.compile(r"\w+")


def normalize_herb_name(value: str) -> str:
    """Preserve the indexer's ASCII and Unicode token/boundary semantics."""
    return " ".join(HERB_TOKENS.findall(value.lower() if value.isascii() else plain(value)))


def fingerprint_rows(rows) -> str:
    raw = json.dumps(
        [HERBS_INDEX_VERSION, sorted(rows)], ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def read_index_catalogs(connection):
    """Two aggregated queries, preserving exact condition terms and all herb owners."""
    conditions = connection.execute(
        "SELECT c.id, c.name, COALESCE(array_agg(DISTINCT s.synonym ORDER BY s.synonym) "
        "FILTER (WHERE s.synonym IS NOT NULL), ARRAY[]::text[]) "
        "FROM medical_conditions c LEFT JOIN medical_condition_synonyms s "
        "ON s.medical_condition_id=c.id GROUP BY c.id, c.name ORDER BY c.id"
    ).fetchall()
    if not conditions:
        raise CatalogUnavailable()
    condition_rows = []
    positions_by_term: dict[str, set[int]] = {}
    seen_names = set()
    for position, (condition_id, name, synonyms) in enumerate(conditions):
        if (
            type(condition_id) is not int
            or condition_id <= 0
            or not isinstance(name, str)
            or not _normalize(name)
            or name != " ".join(name.split())
            or _normalize(name) in seen_names
            or not all(isinstance(term, str) and _normalize(term) for term in synonyms)
        ):
            raise CatalogUnavailable()
        seen_names.add(_normalize(name))
        condition_rows.append([condition_id, name, sorted(set(synonyms))])
        for term in (name, *synonyms):
            positions_by_term.setdefault(term, set()).add(position)

    rows = connection.execute(
        "SELECT h.id, h.family, h.latin, h.ro, h.en, "
        "COALESCE(array_agg(DISTINCT a.name ORDER BY a.name) FILTER "
        "(WHERE a.kind='ro_regional'), ARRAY[]::text[]), "
        "COALESCE(array_agg(DISTINCT a.name ORDER BY a.name) FILTER "
        "(WHERE a.kind='latin_synonyms'), ARRAY[]::text[]), "
        "COALESCE(array_agg(DISTINCT a.name ORDER BY a.name) FILTER "
        "(WHERE a.kind='en_alt'), ARRAY[]::text[]) "
        "FROM herbs h LEFT JOIN herb_aliases a ON a.herb_id=h.id "
        "GROUP BY h.id, h.family, h.latin, h.ro, h.en ORDER BY h.id"
    ).fetchall()
    herbs = [
        Herb(
            id=i,
            family=f,
            latin="" if latin is None else latin,
            ro=r,
            en=e,
            ro_regional=tuple(rr),
            latin_synonyms=tuple(ls),
            en_alt=tuple(ea),
        )
        for i, f, latin, r, e, rr, ls, ea in rows
    ]
    if catalog_problems(
        sorted(herbs, key=lambda h: (_normalize(h.ro), _normalize(h.latin))), source=False
    ):
        raise HerbCatalogUnavailable()
    names: dict[str, set[int]] = {}
    herb_rows = []
    for position, herb in enumerate(herbs):
        normalized = sorted({normalize_herb_name(name) for name in herb.names} - {""})
        if not normalized:
            raise HerbCatalogUnavailable()
        herb_rows.append([herb.id, normalized])
        for name in normalized:
            names.setdefault(name, set()).add(position)
    return (
        tuple(row[0] for row in conditions),
        tuple(h.id for h in herbs),
        MappingProxyType({k: tuple(sorted(v)) for k, v in positions_by_term.items()}),
        tuple((k, tuple(sorted(v))) for k, v in sorted(names.items())),
        fingerprint_rows(condition_rows),
        fingerprint_rows(herb_rows),
    )
