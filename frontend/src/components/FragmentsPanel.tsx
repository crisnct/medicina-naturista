import { useMemo, useState } from "react";
import type { FragmentItem, FragmentsMessage } from "../api/types";

type LexicalFilter = "all" | "yes" | "no";

// Priority is decided per search from the condition the patient named (or its
// synonyms): 1 = in the fragment's title/path, 3 = in its text, 10 = in neither.
const PRIORITY_OPTIONS: { value: number; label: string }[] = [
  { value: 1, label: "1 – afecțiunea e în titlu" },
  { value: 3, label: "3 – afecțiunea e în text" },
  { value: 10, label: "10 – afecțiunea lipsește" },
];

// Semantic-score thresholds, 0.05 to 0.95 in steps of 0.05 (integer math avoids float drift).
const SEMANTIC_OPTIONS = Array.from({ length: 19 }, (_, i) => (i + 1) * 0.05).map((value) => Number(value.toFixed(2)));

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
  minSemantic: number,
): FragmentItem[] {
  return fragments.filter((fragment) => {
    if (minScore > 0 && (fragment.relevancePercent ?? 0) < minScore) return false;
    // Strictly greater than the threshold; fragments without a semantic score never pass.
    if (minSemantic > 0 && !((fragment.semanticScore ?? -Infinity) > minSemantic)) return false;
    if (priority !== "all" && fragment.priority !== priority) return false;
    if (lexical !== "all" && fragment.foundByLexical !== (lexical === "yes")) return false;
    if (document !== "all" && fragment.document !== document) return false;
    return true;
  });
}

export function FragmentsPanel({ message }: { message: FragmentsMessage }) {
  const [open, setOpen] = useState(false);
  const [minScore, setMinScore] = useState(0);
  const [minSemantic, setMinSemantic] = useState(0);
  const [priority, setPriority] = useState<"all" | number>("all");
  const [lexical, setLexical] = useState<LexicalFilter>("all");
  const [documentFilter, setDocumentFilter] = useState<"all" | string>("all");

  // Every source document across ALL fragments (not just the currently
  // filtered ones), so picking a document is always available as an option.
  // Sorted by the displayed file name (A→Z), not by the full path.
  const documentOptions = useMemo(
    () =>
      [...new Set(message.fragments.map((fragment) => fragment.document))].sort((a, b) =>
        fileName(a).localeCompare(fileName(b), "ro", { sensitivity: "base", numeric: true }),
      ),
    [message.fragments],
  );

  const filtered = useMemo(
    () => applyFilters(message.fragments, minScore, priority, lexical, documentFilter, minSemantic),
    [message.fragments, minScore, priority, lexical, documentFilter, minSemantic],
  );
  // Only the documents behind the fragments still visible after filtering.
  const documents = [...new Set(filtered.map((fragment) => fragment.document))];
  const filtersActive = minScore > 0 || minSemantic > 0 || priority !== "all" || lexical !== "all" || documentFilter !== "all";

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
            Scor semantic
            <select value={minSemantic} onChange={(event) => setMinSemantic(Number(event.target.value))}>
              <option value={0}>Toate</option>
              {SEMANTIC_OPTIONS.map((value) => (
                <option key={value} value={value}>
                  {`> ${value.toFixed(2)}`}
                </option>
              ))}
            </select>
          </label>
          <label className="fragments-panel-filter">
            Prioritate
            <select
              value={priority}
              onChange={(event) => setPriority(event.target.value === "all" ? "all" : Number(event.target.value))}
            >
              <option value="all">Toate</option>
              {PRIORITY_OPTIONS.map(({ value, label }) => (
                <option key={value} value={value}>
                  {label}
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
            if (fragment.semanticScore != null) scoreParts.push(`Scor semantic: ${fragment.semanticScore.toFixed(2)}`);
            if (fragment.lexicalScore != null) scoreParts.push(`Scor lexical: ${fragment.lexicalScore.toFixed(2)}`);
            if (fragment.priority !== null) scoreParts.push(`Prioritate ${fragment.priority}`);
            if (fragment.matchLabel) scoreParts.push(fragment.matchLabel);
            return (
              <div className="fragments-panel-fragment" key={index}>
                <p className="fragments-panel-fragment-text">{fragment.text}</p>
                <p className="fragments-panel-fragment-score">
                  {scoreParts.join(", ")}
                  {scoreParts.length > 0 && ","}
                  <br />
                  {fragment.document}
                </p>
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
