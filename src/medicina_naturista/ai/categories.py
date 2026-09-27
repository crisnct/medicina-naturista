"""Category tree loaded from the generated hybrid index.

Lets the patient restrict retrieval to chosen source folders before
searching. The tree itself is derived once, at index build time, from the
folder structure of data/documents (see scripts/build_hybrid_index.py's
build_category_tree()) and written to <index_dir>/categories.json. This
module only loads and exposes that file; it never recomputes the tree.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


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


# Load the category tree written by build_hybrid_index.py, or None when the
# index predates category support (an older index has no categories.json) —
# callers must treat that as "no category filtering available", never as an
# error, so an index built before this feature existed keeps working.
def load_category_tree(index_dir: Path) -> CategoryTree | None:
    path = index_dir / "categories.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
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
