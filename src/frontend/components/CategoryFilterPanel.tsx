import { tr } from "../lib/texts";
import { useState } from "react";
import type { CategoryNode, SearchSignals } from "../api/types";
import { collectRealIds, nodeCheckState, selectedDocumentCount, toggleNode } from "../lib/categoryTree";
import { countOn } from "../lib/searchSignals";

interface Props {
  tree: CategoryNode | null;
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  signals: SearchSignals;
  onSignalsChange: (next: SearchSignals) => void;
}

// The signals of the score the patient can switch on and off, one checkbox each
// (A conditions, B lexical, C semantic — see ai/search.py).
const SIGNAL_OPTIONS: { key: keyof SearchSignals; label: string }[] = [
  { key: "conditions", label: tr("interface.search_conditions") },
  { key: "lexical", label: tr("interface.search_lexical") },
  { key: "semantic", label: tr("interface.search_semantic") },
];

export const LAST_SIGNAL_HINT = tr("interface.search_last_signal_hint");

// "Ce tip de căutare doriți să efectuez?": the last checked box is disabled, so
// the choice can never reach zero signals.
export function SearchSignalsGroup({
  signals,
  onChange,
}: {
  signals: SearchSignals;
  onChange: (next: SearchSignals) => void;
}) {
  const checkedCount = countOn(signals);
  return (
    <fieldset className="search-signals">
      <legend className="search-signals-title">{tr("interface.search_types_title")}</legend>
      {SIGNAL_OPTIONS.map(({ key, label }) => {
        const isLastChecked = signals[key] && checkedCount === 1;
        return (
          <label key={key} className="search-signal-label" title={isLastChecked ? LAST_SIGNAL_HINT : undefined}>
            <input
              type="checkbox"
              className="cat-checkbox"
              checked={signals[key]}
              disabled={isLastChecked}
              onChange={(event) => onChange({ ...signals, [key]: event.target.checked })}
            />
            <span className="cat-label-text">{label}</span>
          </label>
        );
      })}
    </fieldset>
  );
}

export function CategoryFilterPanel({ tree, selected, onChange, signals, onSignalsChange }: Props) {
  if (tree === null) {
    return (
      <section className="category-filter-panel">
        <p className="category-filter-unavailable">
          {tr("interface.categories_unavailable")}</p>
      </section>
    );
  }

  const totalReal = collectRealIds(tree).length;
  const checkedCount = collectRealIds(tree).filter((id) => selected.has(id)).length;
  const status =
    checkedCount === 0
      ? tr("interface.categories_none_selected_warning")
      : checkedCount >= totalReal
        ? tr("interface.categories_all_status")
        : tr(checkedCount === 1 ? "interface.categories_selected_one" : "interface.categories_selected_other", { count: checkedCount });
  const documents = selectedDocumentCount(tree, selected);

  const topLevelNodes = tree.isReal ? [tree, ...tree.children] : tree.children;

  return (
    <section className="category-filter-panel">
      <details className="category-filter-details">
        <summary className="category-filter-summary">
          <span aria-hidden="true">{"🗂️"}</span> {tr("interface.categories_options_title")}<span className="selection-status">{checkedCount === 0 ? tr("interface.categories_none") : checkedCount >= totalReal ? tr("interface.categories_all") : tr("interface.categories_selected_count", { count: checkedCount })}</span>
        </summary>
        <div className="category-filter-body">
          <SearchSignalsGroup signals={signals} onChange={onSignalsChange} />
          <div className="category-filter-toolbar">
            <p className="category-filter-status">{status}</p>
            <div className="category-filter-toolbar-buttons">
              <button type="button" className="category-filter-reset" onClick={() => onChange(new Set(collectRealIds(tree)))}>
                {tr("interface.categories_select_all")}</button>
              <button type="button" className="category-filter-reset" onClick={() => onChange(new Set())}>
                {tr("interface.categories_deselect_all")}</button>
            </div>
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
            {tr(documents === 1 ? "interface.categories_documents_one" : "interface.categories_documents_other", { count: documents })}</p>
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
  const [expanded, setExpanded] = useState(false);

  return (
    <li className="cat-node">
      <div className="cat-row">
        {hasChildren ? (
          <button
            type="button"
            className={`cat-toggle${expanded ? " cat-toggle-open" : ""}`}
            aria-expanded={expanded}
            aria-label={`${expanded ? tr("interface.category_collapse") : tr("interface.category_expand")} ${node.label}`}
            title={expanded ? tr("interface.category_collapse") : tr("interface.category_expand")}
            onClick={() => setExpanded((open) => !open)}
          >
            <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true" focusable="false">
              <path d="M2.5 4.25 6 7.75l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        ) : (
          <span className="cat-toggle cat-toggle-spacer" aria-hidden="true" />
        )}
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
            {node.label} <span className="cat-count">{"("}{node.totalDocuments}{")"}</span>
          </span>
        </label>
      </div>
      {hasChildren && expanded && (
        <ul>
          {node.children.map((child) => (
            <CategoryNodeRow key={child.id} node={child} selected={selected} onChange={onChange} />
          ))}
        </ul>
      )}
    </li>
  );
}
