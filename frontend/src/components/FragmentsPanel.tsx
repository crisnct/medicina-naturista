import { useMemo, useState } from "react";
import type { FragmentItem, FragmentsMessage } from "../api/types";

type LexicalFilter = "all" | "yes" | "no";

// The document's relative path can be several folders deep; the filter shows
// just the filename (the full path stays the option's value and its title).
function fileName(path: string): string {
  return path.split("/").pop() || path;
}

// Keep only fragments matching every active filter (score, priority, lexical
// match, source document); each filter left at its "no restriction" value
// passes everything.
function applyFilters(
  fragments: FragmentItem[],
  minScore: number,
  priority: "all" | number,
  lexical: LexicalFilter,
  document: "all" | string,
): FragmentItem[] {
  return fragments.filter((fragment) => {
    if (minScore > 0 && (fragment.relevancePercent ?? 0) < minScore) return false;
    if (priority !== "all" && fragment.priority !== priority) return false;
    if (lexical !== "all" && fragment.foundByLexical !== (lexical === "yes")) return false;
    if (document !== "all" && fragment.document !== document) return false;
    return true;
  });
}

export function FragmentsPanel({ message }: { message: FragmentsMessage }) {
  const [open, setOpen] = useState(false);
  const [minScore, setMinScore] = useState(0);
  const [priority, setPriority] = useState<"all" | number>("all");
  const [lexical, setLexical] = useState<LexicalFilter>("all");
  const [documentFilter, setDocumentFilter] = useState<"all" | string>("all");

  const priorityOptions = useMemo(
    () =>
      [...new Set(message.fragments.map((fragment) => fragment.priority).filter((value): value is number => value !== null))].sort(
        (a, b) => a - b,
      ),
    [message.fragments],
  );
  // Every source document across ALL fragments (not just the currently
  // filtered ones), so picking a document is always available as an option.
  const documentOptions = useMemo(
    () => [...new Set(message.fragments.map((fragment) => fragment.document))].sort((a, b) => a.localeCompare(b)),
    [message.fragments],
  );

  const filtered = useMemo(
    () => applyFilters(message.fragments, minScore, priority, lexical, documentFilter),
    [message.fragments, minScore, priority, lexical, documentFilter],
  );
  // Only the documents behind the fragments still visible after filtering.
  const documents = [...new Set(filtered.map((fragment) => fragment.document))];
  const filtersActive = minScore > 0 || priority !== "all" || lexical !== "all" || documentFilter !== "all";

  return (
    <details className="fragments-panel-inner" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary className="fragments-panel-banner">
        Am găsit {message.fragmentsCount} fragmente relevante în {message.documentsCount} documente locale (le puteți
        vedea mai jos). Dacă vi se par potrivite, apăsați „Generează rețeta”.
      </summary>
      <div className="fragments-panel-list">
        <div className="fragments-panel-filters">
          <label className="fragments-panel-filter">
            Scor minim
            <select value={minScore} onChange={(event) => setMinScore(Number(event.target.value))}>
              <option value={0}>Toate</option>
              <option value={25}>≥ 25%</option>
              <option value={50}>≥ 50%</option>
              <option value={75}>≥ 75%</option>
              <option value={90}>≥ 90%</option>
            </select>
          </label>
          <label className="fragments-panel-filter">
            Prioritate
            <select
              value={priority}
              onChange={(event) => setPriority(event.target.value === "all" ? "all" : Number(event.target.value))}
            >
              <option value="all">Toate</option>
              {priorityOptions.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label className="fragments-panel-filter">
            Găsire lexicală
            <select value={lexical} onChange={(event) => setLexical(event.target.value as LexicalFilter)}>
              <option value="all">Toate</option>
              <option value="yes">Da</option>
              <option value="no">Nu</option>
            </select>
          </label>
          <label className="fragments-panel-filter fragments-panel-filter-document">
            Document
            <select value={documentFilter} onChange={(event) => setDocumentFilter(event.target.value)}>
              <option value="all">Toate</option>
              {documentOptions.map((document) => (
                <option key={document} value={document} title={document}>
                  {fileName(document)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="fragments-panel-documents">
          <p className="fragments-panel-documents-title">Documente ({documents.length})</p>
          <ul className="fragments-panel-documents-list">
            {documents.map((document) => (
              <li key={document}>{document}</li>
            ))}
          </ul>
        </div>
        {filtered.length === 0 ? (
          <p className="fragments-panel-empty">Niciun fragment nu corespunde filtrelor selectate.</p>
        ) : (
          filtered.map((fragment, index) => {
            const scoreParts: string[] = [];
            if (fragment.relevancePercent !== null) scoreParts.push(`Scor relevanță: ${Math.round(fragment.relevancePercent)}%`);
            if (fragment.priority !== null) scoreParts.push(`Prioritate ${fragment.priority}`);
            if (fragment.matchLabel) scoreParts.push(fragment.matchLabel);
            scoreParts.push(fragment.document);
            return (
              <div className="fragments-panel-fragment" key={index}>
                <p className="fragments-panel-fragment-text">{fragment.text}</p>
                <p className="fragments-panel-fragment-score">{scoreParts.join(", ")}</p>
              </div>
            );
          })
        )}
        <p className="fragments-panel-summary">
          {filtersActive
            ? `Afișate: ${filtered.length} din ${message.fragmentsCount} fragmente (filtrate), din ${documents.length} documente.`
            : `Total: ${message.fragmentsCount} fragmente din ${message.documentsCount} documente.`}
        </p>
      </div>
    </details>
  );
}
