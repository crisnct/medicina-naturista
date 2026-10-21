import { tr } from "../lib/texts";
import { useMemo, useState } from "react";
import type { FragmentItem, FragmentsMessage } from "../api/types";
import { MIN_SCORE_OPTIONS, reachesMinScore } from "../lib/scoreFilter";
import { ALL_SIGNALS } from "../lib/searchSignals";
import { DoctorAvatar } from "./DoctorAvatar";

type LexicalFilter = "all" | "yes" | "no";
type ConditionFilter = "all" | "title" | "text" | "none";

// Where the condition the patient named was found in the fragment (decided per
// search): in its title, in its text, or in neither.
const CONDITION_OPTIONS: { value: Exclude<ConditionFilter, "all">; label: string }[] = [
  { value: "title", label: tr("interface.fragments_in_title") },
  { value: "text", label: tr("interface.fragments_in_text") },
  { value: "none", label: tr("interface.fragments_missing") },
];

// Label of the score line for a fragment's condition match; nothing when it has none.
const CONDITION_LABELS = { title: tr("interface.fragments_condition_in_title"), text: tr("interface.fragments_condition_in_text") } as const;

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
    if (!reachesMinScore(fragment.relevancePercent, minScore)) return false;
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
    <section className="search-results-panel">
      <div className="search-results-summary chatbot-message-header">
        <DoctorAvatar />
        <p>{tr("interface.fragments_found_prefix")}<strong>{message.fragmentsCount} {tr("interface.fragments_label")}</strong> {tr("interface.fragments_relevant_in")}<strong>{message.documentsCount} {tr("interface.fragments_documents_label")}</strong></p>
      </div>
      <details className="fragments-panel-inner" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
        <summary className="fragments-panel-banner">
          {tr("interface.fragments_show_sources")}</summary>
        <div className="fragments-panel-list">
          <section className="display-filter-options" aria-label={tr("interface.fragments_filter_heading")}>
            <h4>{tr("interface.fragments_filter_heading")}{filtersActive ? tr("interface.fragments_filtered_count", { visible_count: filtered.length }) : ""}</h4>
            <p>{tr("interface.fragments_display_filters_hint")}</p>
            <div className="fragments-panel-filters">
              <label className="fragments-panel-filter">
                {tr("common.minimum_score")}<select value={minScore} onChange={(event) => setMinScore(Number(event.target.value))}>
                  {MIN_SCORE_OPTIONS.map(({ value, label }) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              {signals.semantic && (
                <label className="fragments-panel-filter">
                  {tr("interface.fragments_semantic_score_label")}<select value={minSemantic} onChange={(event) => setMinSemantic(Number(event.target.value))}>
                    <option value={0}>{tr("common.all")}</option>
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
                  {tr("interface.fragments_condition")}<select value={condition} onChange={(event) => setCondition(event.target.value as ConditionFilter)}>
                    <option value="all">{tr("common.all")}</option>
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
                  {tr("interface.fragments_lexical_match")}<select value={lexical} onChange={(event) => setLexical(event.target.value as LexicalFilter)}>
                    <option value="all">{tr("common.all")}</option>
                    <option value="yes">{tr("interface.yes")}</option>
                    <option value="no">{tr("interface.no")}</option>
                  </select>
                </label>
              )}
              <label className="fragments-panel-filter fragments-panel-filter-document">
                {tr("interface.fragments_document")}<select value={documentFilter} onChange={(event) => setDocumentFilter(event.target.value)}>
                  <option value="all">{tr("common.all")}</option>
                  {documentOptions.map((document) => (
                    <option key={document} value={document} title={document}>
                      {fileName(document)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </section>
          <div className="fragments-panel-documents">
            <p className="fragments-panel-documents-title">{tr("interface.fragments_documents_heading")}{documents.length}{")"}</p>
            <ul className="fragments-panel-documents-list">
              {documents.map((document) => (
                <li key={document}>{document}</li>
              ))}
            </ul>
          </div>
          {filtered.length === 0 ? (
            <p className="fragments-panel-empty">{tr("interface.fragments_none_match")}</p>
          ) : (
            filtered.map((fragment, index) => {
              const scoreParts: string[] = [];
              if (fragment.relevancePercent !== null) scoreParts.push(tr("interface.fragments_relevance_score", { score: Math.round(fragment.relevancePercent) }));
              if (signals.semantic && fragment.semanticScore != null)
                scoreParts.push(tr("interface.fragments_semantic_score", { score: fragment.semanticScore.toFixed(2) }));
              if (signals.lexical && fragment.lexicalScore != null)
                scoreParts.push(tr("interface.fragments_lexical_score", { score: fragment.lexicalScore.toFixed(2) }));
              if (signals.conditions && fragment.conditionMatch !== null)
                scoreParts.push(CONDITION_LABELS[fragment.conditionMatch]);
              if (signals.lexical && fragment.matchLabel) scoreParts.push(fragment.matchLabel);
              return (
                <div className="fragments-panel-fragment" key={index}>
                  <p className="fragments-panel-fragment-text">{fragment.text}</p>
                  <p className="fragment-source">{fragment.document}</p>
                  {scoreParts.length > 0 && (
                    <p className="fragments-panel-fragment-score">{scoreParts.join(", ")}</p>
                  )}
                </div>
              );
            })
          )}
          <p className="fragments-panel-summary">
            {filtersActive
              ? tr("interface.fragments_filtered_summary", { visible_count: filtered.length, total_count: message.fragmentsCount, document_count: documents.length, characters: totalChars })
              : tr("interface.fragments_total_summary", { count: message.fragmentsCount, document_count: message.documentsCount, characters: totalChars })}
          </p>
        </div>
      </details>
    </section>
  );
}
