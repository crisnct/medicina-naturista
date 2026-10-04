"""Category tree derived from the source documents stored in Postgres.

Lets the patient restrict retrieval to chosen source folders before
searching. The tree is derived on demand from each document's category_id
(its containing folder, relative to the source root — see build_category_tree()
below, and scripts/build_hybrid_index.py for how category_id is assigned at
sync time). Nothing here is cached to disk; `load_category_tree()` queries
the `documents` table fresh each time it's called.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from psycopg.rows import namedtuple_row

from backend.ai.db import get_pool

# Category id used for files placed directly in the source root, with no
# containing folder.
ROOT_CATEGORY_ID = ""


@dataclass(frozen=True)
class CategoryNode:
    id: str
    label: str
    parent: str | None
    children: tuple[str, ...]
    # Documents whose containing folder is exactly this category.
    own_documents: int
    # own_documents plus every descendant category's own_documents.
    total_documents: int


@dataclass(frozen=True)
class CategoryTree:
    root_id: str
    nodes: dict[str, CategoryNode]

    # Category ids that actually tag a chunk (own_documents > 0) — the only
    # ids valid as a retrieval filter. A purely structural ancestor (a folder
    # holding only subfolders, no document of its own) is never a chunk's
    # category_id, so it must never be passed to search.rank() directly.
    def known_ids(self) -> frozenset[str]:
        return frozenset(node.id for node in self.nodes.values() if node.own_documents > 0)


# Depth of a category id in the tree: the root ("") is depth 0, a top-level
# folder is depth 1, and each "/" below that adds one more level.
def _category_depth(category_id: str) -> int:
    return 0 if category_id == ROOT_CATEGORY_ID else category_id.count("/") + 1


# Derive the full category tree from the folder each source document lives
# in (each item's category_id attribute — a SourceFile at sync time, or a
# plain row from `documents` at load time): every folder that directly holds
# at least one document becomes a category, and every one of ITS ancestor
# folders (even ones holding no document directly, only subfolders) becomes a
# purely structural parent category. Only categories with own_documents > 0
# ever tag a chunk — an ancestor-only category exists in the tree for
# navigation/UI purposes but is never itself a valid retrieval filter.
def build_category_tree(sources: Sequence[object]) -> dict[str, object]:
    own_documents: dict[str, int] = {}
    for item in sources:
        category_id = item.category_id
        own_documents[category_id] = own_documents.get(category_id, 0) + 1

    all_ids: set[str] = {ROOT_CATEGORY_ID}
    for category_id in own_documents:
        prefix = ROOT_CATEGORY_ID
        all_ids.add(prefix)
        if category_id == ROOT_CATEGORY_ID:
            continue
        for part in category_id.split("/"):
            prefix = f"{prefix}/{part}" if prefix else part
            all_ids.add(prefix)

    parent_of: dict[str, str | None] = {ROOT_CATEGORY_ID: None}
    children: dict[str, list[str]] = {category_id: [] for category_id in all_ids}
    for category_id in all_ids:
        if category_id == ROOT_CATEGORY_ID:
            continue
        parent = category_id.rsplit("/", 1)[0] if "/" in category_id else ROOT_CATEGORY_ID
        parent_of[category_id] = parent
        children[parent].append(category_id)
    for sibling_ids in children.values():
        sibling_ids.sort(key=str.casefold)

    # Accumulate each category's own document count into its own total, then
    # add that total into its parent's total, deepest categories first, so a
    # parent's total is only ever added upward after every one of its own
    # descendants has already been folded into it.
    total_documents: dict[str, int] = {category_id: own_documents.get(category_id, 0) for category_id in all_ids}
    for category_id in sorted(all_ids, key=_category_depth, reverse=True):
        parent = parent_of[category_id]
        if parent is not None:
            total_documents[parent] += total_documents[category_id]

    nodes = {
        category_id: {
            "id": category_id,
            "label": "(fără categorie)" if category_id == ROOT_CATEGORY_ID else category_id.rsplit("/", 1)[-1],
            "parent": parent_of[category_id],
            "children": children[category_id],
            "own_documents": own_documents.get(category_id, 0),
            "total_documents": total_documents[category_id],
        }
        for category_id in all_ids
    }
    return {"version": 1, "root_id": ROOT_CATEGORY_ID, "nodes": nodes}


# Convert build_category_tree()'s plain-dict shape into CategoryTree dataclasses.
def _tree_from_payload(payload: dict[str, object]) -> CategoryTree:
    nodes = {
        node_id: CategoryNode(
            id=raw["id"],
            label=raw["label"],
            parent=raw["parent"],
            children=tuple(raw["children"]),
            own_documents=int(raw["own_documents"]),
            total_documents=int(raw["total_documents"]),
        )
        for node_id, raw in payload["nodes"].items()
    }
    return CategoryTree(root_id=payload["root_id"], nodes=nodes)


# Load the category tree from the `documents` table, or None when no document
# has been synced yet — callers must treat that as "no category filtering
# available", never as an error, matching the pre-migration behaviour where an
# index built before category support existed had no categories.json.
def load_category_tree() -> CategoryTree | None:
    with get_pool().connection() as connection:
        with connection.cursor(row_factory=namedtuple_row) as cursor:
            rows = cursor.execute("SELECT category_id FROM documents").fetchall()
    if not rows:
        return None
    return _tree_from_payload(build_category_tree(rows))
