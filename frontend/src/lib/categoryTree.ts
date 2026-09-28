import type { CategoryNode } from "../api/types";

// Every "real" (own_documents > 0) category id under a node, including the
// node itself when it is real. A purely structural branch (subfolders only)
// contributes nothing of its own — matching CategoryTree.known_ids() on the
// backend, the only ids that are ever valid retrieval filters.
export function collectRealIds(node: CategoryNode): string[] {
  const ids = node.isReal ? [node.id] : [];
  for (const child of node.children) ids.push(...collectRealIds(child));
  return ids;
}

export type CheckState = "checked" | "unchecked" | "mixed";

// A node's own checkbox state, derived from how many of its real descendants
// (including itself) are selected — checked, unchecked, or a tri-state mix.
export function nodeCheckState(node: CategoryNode, selected: ReadonlySet<string>): CheckState {
  const realIds = collectRealIds(node);
  if (realIds.length === 0) return "unchecked";
  const checkedCount = realIds.filter((id) => selected.has(id)).length;
  if (checkedCount === 0) return "unchecked";
  if (checkedCount === realIds.length) return "checked";
  return "mixed";
}

// Checking (or unchecking) a node cascades the same state to every real id
// under it — clicking a mixed box always selects everything beneath it.
export function toggleNode(node: CategoryNode, selected: ReadonlySet<string>, checked: boolean): Set<string> {
  const next = new Set(selected);
  for (const id of collectRealIds(node)) {
    if (checked) next.add(id);
    else next.delete(id);
  }
  return next;
}

// Sum of ownDocuments over every selected real node — never totalDocuments,
// which would double-count a folder together with its own subfolders if both
// ended up selected.
export function selectedDocumentCount(tree: CategoryNode, selected: ReadonlySet<string>): number {
  let total = 0;
  const walk = (node: CategoryNode) => {
    if (node.isReal && selected.has(node.id)) total += node.ownDocuments;
    node.children.forEach(walk);
  };
  walk(tree);
  return total;
}
