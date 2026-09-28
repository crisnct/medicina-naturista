import type { CategoryNode } from "../api/types";
import { collectRealIds, nodeCheckState, selectedDocumentCount, toggleNode } from "../lib/categoryTree";

interface Props {
  tree: CategoryNode | null;
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
}

export function CategoryFilterPanel({ tree, selected, onChange }: Props) {
  if (tree === null) {
    return (
      <section className="category-filter-panel">
        <p className="category-filter-unavailable">
          Filtrarea pe categorii nu este disponibilă până la sincronizarea indexului.
        </p>
      </section>
    );
  }

  const totalReal = collectRealIds(tree).length;
  const checkedCount = collectRealIds(tree).filter((id) => selected.has(id)).length;
  const status =
    checkedCount === 0
      ? "Nicio sursă selectată — căutarea va fi respinsă până bifați cel puțin una."
      : checkedCount >= totalReal
        ? "Se caută în toate sursele."
        : `Se caută doar în ${checkedCount} categorie${checkedCount === 1 ? "" : "i"} selectată${checkedCount === 1 ? "" : "e"}.`;
  const documents = selectedDocumentCount(tree, selected);

  const topLevelNodes = tree.isReal ? [tree, ...tree.children] : tree.children;

  return (
    <section className="category-filter-panel">
      <details className="category-filter-details">
        <summary className="category-filter-summary">
          <span aria-hidden="true">🗂️</span> Setează sursele
        </summary>
        <div className="category-filter-body">
          <div className="category-filter-toolbar">
            <p className="category-filter-status">{status}</p>
            <button type="button" className="category-filter-reset" onClick={() => onChange(new Set(collectRealIds(tree)))}>
              Selectează tot
            </button>
          </div>
          <ul className="category-tree">
            {topLevelNodes.map((node) => (
              <CategoryNodeRow
                key={node.id}
                node={node}
                forceLeaf={node.id === tree.id}
                selected={selected}
                onChange={onChange}
              />
            ))}
          </ul>
          <p className="category-filter-total">
            Total: {documents} document{documents === 1 ? "" : "e"} selectate.
          </p>
        </div>
      </details>
    </section>
  );
}

function CategoryNodeRow({
  node,
  forceLeaf = false,
  selected,
  onChange,
}: {
  node: CategoryNode;
  forceLeaf?: boolean;
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
}) {
  const state = nodeCheckState(node, selected);
  const hasChildren = node.children.length > 0 && !forceLeaf;

  return (
    <li className="cat-node">
      <div className="cat-row">
        <span className="cat-toggle cat-toggle-spacer" aria-hidden="true" />
        <label className="cat-check-label">
          <input
            type="checkbox"
            className="cat-checkbox"
            checked={state === "checked"}
            ref={(input) => {
              if (input) input.indeterminate = state === "mixed";
            }}
            onChange={(event) => onChange(toggleNode(node, selected, event.target.checked))}
          />
          <span className="cat-label-text">
            {node.label} <span className="cat-count">({node.totalDocuments})</span>
          </span>
        </label>
      </div>
      {hasChildren && (
        <details className="cat-children" open={false}>
          <summary className="cat-children-summary">Extinde</summary>
          <ul>
            {node.children.map((child) => (
              <CategoryNodeRow key={child.id} node={child} selected={selected} onChange={onChange} />
            ))}
          </ul>
        </details>
      )}
    </li>
  );
}
