import { useMemo, useState } from "react";
import type { FragmentItem, FragmentsMessage } from "../api/types";
import { ALL_SIGNALS } from "../lib/searchSignals";

type LexicalFilter = "all" | "yes" | "no";
type ConditionFilter = "all" | "title" | "text" | "none";

// Where the condition the patient named was found in the fragment (decided per
// search): in its title, in its text, or in neither.
const CONDITION_OPTIONS: { value: Exclude<ConditionFilter, "all">; label: string }[] = [
  { value: "title", label: "În titlu" },
  { value: "text", label: "În text" },
  { value: "none", label: "Lipsește" },
];

// Label of the score line for a fragment's condition match; nothing when it has none.
const CONDITION_LABELS = { title: "Afecțiune în titlu", text: "Afecțiune în text" } as const;

// Semantic-score thresholds, 0.05 to 0.95 in steps of 0.05 (integer math avoids float drift).
const SEMANTIC_OPTIONS = Array.from({ length: 19 }, (_, i) => (i + 1) * 0.05).map((value) => Number(value.toFixed(2)));

// The document's relative path can be several folders deep; the filter shows
// just the filename (the full path stays the option's value and its title).
function fileName(path: string): string {
  return path.split("/").pop() || path;
}

// Keep only fragments matching every active filter (score, condition, lexical
// match, source document); each filter left at its "no restriction" value
// passes everything.
function applyFilters(
  fragments: FragmentItem[],
  minScore: number,
  condition: ConditionFilter,
  lexical: LexicalFilter,
  document: "all" | string,
  minSemantic: number,
): FragmentItem[] {
  return fragments.filter((fragment) => {
    if (minScore > 0 && (fragment.relevancePercent ?? 0) < minScore) return false;
    // Strictly greater than the threshold; fragments without a semantic score never pass.
    if (minSemantic > 0 && !((fragment.semanticScore ?? -Infinity) > minSemantic)) return false;
    if (condition !== "all" && (fragment.conditionMatch ?? "none") !== condition) return false;
    if (lexical !== "all" && fragment.foundByLexical !== (lexical === "yes")) return false;
    if (document !== "all" && fragment.document !== document) return false;
    return true;
  });
}

export function FragmentsPanel({ message }: { message: FragmentsMessage }) {
  // The signals this search was scored with decide which score components and
  // filters make sense; a message from before the choice existed had them all.
  const signals = message.signals ?? ALL_SIGNALS;
  const [open, setOpen] = useState(false);
  const [minScore, setMinScore] = useState(0);
  const [minSemantic, setMinSemantic] = useState(0);
  const [condition, setCondition] = useState<ConditionFilter>("all");
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
    () => applyFilters(message.fragments, minScore, condition, lexical, documentFilter, minSemantic),
    [message.fragments, minScore, condition, lexical, documentFilter, minSemantic],
  );
  // Only the documents behind the fragments still visible after filtering.
  const documents = [...new Set(filtered.map((fragment) => fragment.document))];
  // Characters of the fragment texts currently shown (after filtering).
  const totalChars = filtered.reduce((sum, fragment) => sum + fragment.text.length, 0).toLocaleString("ro-RO");
  const filtersActive = minScore > 0 || minSemantic > 0 || condition !== "all" || lexical !== "all" || documentFilter !== "all";

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
          {signals.semantic && (
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
          )}
          {signals.conditions && (
            <label className="fragments-panel-filter">
              Afecțiune
              <select value={condition} onChange={(event) => setCondition(event.target.value as ConditionFilter)}>
                <option value="all">Toate</option>
                {CONDITION_OPTIONS.map(({ value, label }) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          )}
          {signals.lexical && (
            <label className="fragments-panel-filter">
              Găsire lexicală
              <select value={lexical} onChange={(event) => setLexical(event.target.value as LexicalFilter)}>
                <option value="all">Toate</option>
                <option value="yes">Da</option>
                <option value="no">Nu</option>
              </select>
            </label>
          )}
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
            if (signals.semantic && fragment.semanticScore != null)
              scoreParts.push(`Scor semantic: ${fragment.semanticScore.toFixed(2)}`);
            if (signals.lexical && fragment.lexicalScore != null)
              scoreParts.push(`Scor lexical: ${fragment.lexicalScore.toFixed(2)}`);
            if (signals.conditions && fragment.conditionMatch !== null)
              scoreParts.push(CONDITION_LABELS[fragment.conditionMatch]);
            if (signals.lexical && fragment.matchLabel) scoreParts.push(fragment.matchLabel);
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
            ? `Afișate: ${filtered.length} din ${message.fragmentsCount} fragmente (filtrate), din ${documents.length} documente, ${totalChars} caractere.`
            : `Total: ${message.fragmentsCount} fragmente din ${message.documentsCount} documente, ${totalChars} caractere.`}
        </p>
      </div>
    </details>
  );
}
