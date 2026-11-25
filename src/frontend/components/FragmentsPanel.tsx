import { locale, tr } from "../lib/texts";
import { useId, useMemo, useState } from "react";
import type { FragmentItem, FragmentsMessage } from "../api/types";
import { useMinScore } from "../hooks/useMinScore";
import { MIN_SCORE_OPTIONS, reachesMinScore } from "../lib/scoreFilter";
import { ALL_SIGNALS } from "../lib/searchSignals";
import { DoctorAvatar } from "./DoctorAvatar";
import { HighlightedSource } from "./HerbEvidencePanel";

type ConditionFilter = "all" | "title" | "text" | "none";

// Where the condition the patient named was found in the fragment (decided per
// search): in its title, in its text, or in neither.
const CONDITION_OPTIONS: { value: Exclude<ConditionFilter, "all">; label: string }[] = [
  { value: "title", get label() { return tr("interface.fragments_in_title"); } },
  { value: "text", get label() { return tr("interface.fragments_in_text"); } },
  { value: "none", get label() { return tr("interface.fragments_missing"); } },
];

// Label of the score line for a fragment's condition match; nothing when it has none.
const CONDITION_LABELS = { get title() { return tr("interface.fragments_condition_in_title"); }, get text() { return tr("interface.fragments_condition_in_text"); } } as const;

// Cosine-similarity thresholds, 0.30 to 0.80 in steps of 0.05, then 0.90: the band Qwen3 cosines of the
// returned fragments sit in (p10 0.34, p99 0.58; 0.75 for the top 20 of the eval queries).
// Lexical-match thresholds (percent of the best BM25 of the search): the search's own tie
// tolerance first, then steps of 10; a value is offered only from the tolerance upwards.
const LEXICAL_STEPS = [10, 20, 30, 40, 50, 60, 70, 80, 90];
function lexicalOptions(tolerance: number): number[] {
  const first = Math.round(tolerance * 100 * 100) / 100;
  return [first, ...LEXICAL_STEPS.filter((value) => value > first)];
}

const SEMANTIC_OPTIONS = [
  ...Array.from({ length: 11 }, (_, i) => 0.3 + i * 0.05).map((value) => Number(value.toFixed(2))),
  0.9,
];

// The document's relative path can be several folders deep; the filter shows
// just the filename (the full path stays the option's value and its title).
function fileName(path: string): string {
  return path.split("/").pop() || path;
}

interface Filters {
  minScore: number;
  condition: ConditionFilter;
  minLexical: number;
  document: "all" | string;
  minSemantic: number;
}

// Keep only fragments matching every active filter (score, similarity, condition, lexical
// match, source document); each filter left at its "no restriction" value
// passes everything. `skip` leaves one filter out, to see which of its values
// still have fragments behind them.
function applyFilters(fragments: FragmentItem[], filters: Filters, skip?: keyof Filters): FragmentItem[] {
  const { minScore, condition, minLexical, document, minSemantic } = filters;
  return fragments.filter((fragment) => {
    if (skip !== "minScore" && !reachesMinScore(fragment.relevancePercent, minScore)) return false;
    // At least the threshold; fragments without a cosine similarity never pass.
    if (skip !== "minSemantic" && minSemantic > 0 && !((fragment.semanticSimilarity ?? -Infinity) >= minSemantic)) return false;
    if (skip !== "condition" && condition !== "all" && (fragment.conditionMatch ?? "none") !== condition) return false;
    // At least the threshold (percent); fragments the lexical search did not find never pass.
    if (skip !== "minLexical" && minLexical > 0 && !((fragment.lexicalPercent ?? -Infinity) >= minLexical)) return false;
    if (skip !== "document" && document !== "all" && fragment.document !== document) return false;
    return true;
  });
}

// A threshold stays in the list only while some fragment reaches it; the value
// already chosen is always kept, so the select never shows something else.
function reachable(values: number[], selected: number, best: number): number[] {
  return values.filter((value) => value === selected || value <= best + 1e-9);
}

export function FragmentsPanel({ message }: { message: FragmentsMessage }) {
  const filtersId = `fragment-filters-${useId()}`;
  // The signals this search was scored with decide which score components and
  // filters make sense; a message from before the choice existed had them all.
  const signals = message.signals ?? ALL_SIGNALS;
  const [open, setOpen] = useState(false);
  const [minScore, setMinScore] = useMinScore(message.searchId);
  const [minSemantic, setMinSemantic] = useState(0);
  const [condition, setCondition] = useState<ConditionFilter>("all");
  const [minLexical, setMinLexical] = useState(0);
  const [documentFilter, setDocumentFilter] = useState<"all" | string>("all");

  // Every source document across ALL fragments (not just the currently
  // filtered ones), so picking a document is always available as an option.
  // Sorted by the displayed file name (A→Z), not by the full path.
  const filters = useMemo<Filters>(
    () => ({ minScore, condition, minLexical, document: documentFilter, minSemantic }),
    [minScore, condition, minLexical, documentFilter, minSemantic],
  );
  const filtered = useMemo(() => applyFilters(message.fragments, filters), [message.fragments, filters]);

  // Each filter offers only the values that still leave at least one fragment
  // under the OTHER active filters; its own current choice is always kept.
  const options = useMemo(() => {
    const others = (skip: keyof Filters) => applyFilters(message.fragments, filters, skip);
    const best = (skip: keyof Filters, read: (fragment: FragmentItem) => number) =>
      Math.max(-Infinity, ...others(skip).map(read));
    const bestScore = best("minScore", (fragment) => fragment.relevancePercent ?? 0);
    const bestSemantic = best("minSemantic", (fragment) => fragment.semanticSimilarity ?? -Infinity);
    const bestLexical = best("minLexical", (fragment) => fragment.lexicalPercent ?? -Infinity);
    const conditions = new Set(others("condition").map((fragment) => fragment.conditionMatch ?? "none"));
    const documents = new Set(others("document").map((fragment) => fragment.document));
    return {
      scores: MIN_SCORE_OPTIONS.filter(({ value }) => value === 0 || value === minScore || value <= bestScore),
      semantic: reachable(
        SEMANTIC_OPTIONS.filter((value) => value >= (message.minSemanticSimilarity ?? 0) - 1e-9),
        minSemantic,
        bestSemantic,
      ),
      lexical: reachable(lexicalOptions(message.lexicalTieTolerance ?? 0.05), minLexical, bestLexical),
      conditions: CONDITION_OPTIONS.filter(({ value }) => value === condition || conditions.has(value)),
      // Sorted by the displayed file name (A→Z), not by the full path.
      documents: [...new Set([...documents, ...(documentFilter === "all" ? [] : [documentFilter])])].sort((a, b) =>
        fileName(a).localeCompare(fileName(b), "ro", { sensitivity: "base", numeric: true }),
      ),
    };
  }, [message.fragments, message.minSemanticSimilarity, message.lexicalTieTolerance, filters, minScore, minSemantic, minLexical, condition, documentFilter]);
  // Only the documents behind the fragments still visible after filtering.
  const documents = [...new Set(filtered.map((fragment) => fragment.document))];
  // Characters of the fragment texts currently shown (after filtering).
  const foundChars = message.fragments.reduce((sum, fragment) => sum + fragment.text.length, 0).toLocaleString(locale());
  const totalChars = filtered.reduce((sum, fragment) => sum + fragment.text.length, 0).toLocaleString(locale());
  const filtersActive = minScore > 0 || minSemantic > 0 || condition !== "all" || minLexical > 0 || documentFilter !== "all";

  return (
    <section className="search-results-panel">
      <div className="search-results-summary chatbot-message-header">
        <DoctorAvatar />
        <p>{tr("interface.fragments_found_prefix")}<strong>{message.fragmentsCount} {tr("interface.fragments_label")}</strong> {tr("interface.fragments_relevant_in")}<strong>{message.documentsCount} {tr("interface.fragments_documents_label")}</strong>{tr("interface.fragments_characters_prefix")}<strong>{foundChars} {tr("interface.fragments_characters_label")}</strong></p>
      </div>
      <details className="fragments-panel-inner" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
        <summary className="fragments-panel-banner">
          {tr("interface.fragments_show_sources")}</summary>
        <div className="fragments-panel-list">
          <section id={filtersId} className="display-filter-options" aria-label={tr("interface.fragments_filter_heading")}>
            <h4>{tr("interface.fragments_filter_heading")}{tr("interface.fragments_filtered_count", { visible_count: filtered.length, characters: totalChars })}</h4>
            <p>{tr("interface.fragments_display_filters_hint")}</p>
            <div className="fragments-panel-filters">
              <label className="fragments-panel-filter">
                {tr("common.minimum_score")}<select value={minScore} onChange={(event) => setMinScore(Number(event.target.value))}>
                  {options.scores.map(({ value, label }) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              {signals.conditions && (
                <label className="fragments-panel-filter">
                  {tr("interface.fragments_condition")}<select value={condition} onChange={(event) => setCondition(event.target.value as ConditionFilter)}>
                    <option value="all">{tr("common.all")}</option>
                    {options.conditions.map(({ value, label }) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {signals.semantic && (
                <label className="fragments-panel-filter">
                  {tr("interface.fragments_semantic_score_label")}<select value={minSemantic} onChange={(event) => setMinSemantic(Number(event.target.value))}>
                    <option value={0}>{tr("common.all")}</option>
                    {options.semantic.map((value) => (
                      <option key={value} value={value}>
                        {`≥ ${Math.round(value * 100)}%`}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {signals.lexical && (
                <label className="fragments-panel-filter">
                  {tr("interface.fragments_lexical_match")}<select value={minLexical} onChange={(event) => setMinLexical(Number(event.target.value))}>
                    <option value={0}>{tr("common.all")}</option>
                    {options.lexical.map((value) => (
                      <option key={value} value={value}>
                        {`≥ ${value}%`}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <label className="fragments-panel-filter fragments-panel-filter-document">
                {tr("interface.fragments_document")}<select value={documentFilter} onChange={(event) => setDocumentFilter(event.target.value)}>
                  <option value="all">{tr("common.all")}</option>
                  {options.documents.map((document) => (
                    <option key={document} value={document} title={document}>
                      {fileName(document)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </section>
          {(signals.conditions || signals.lexical) && (
            <p className="fragments-panel-legend">
              {signals.conditions && <span><mark className="herb-evidence-mark-searched">{tr("interface.fragments_legend_searched")}</mark></span>}
              {signals.lexical && <span><mark className="herb-evidence-mark-lexical">{tr("interface.fragments_legend_lexical")}</mark></span>}
            </p>
          )}
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
              if (signals.conditions && fragment.conditionMatch !== null)
                scoreParts.push(CONDITION_LABELS[fragment.conditionMatch]);
              if (signals.semantic && fragment.semanticRank != null)
                scoreParts.push(tr("interface.fragments_semantic_rank", { rank: fragment.semanticRank }));
              if (signals.lexical && fragment.lexicalRank != null)
                scoreParts.push(tr("interface.fragments_lexical_rank", { rank: fragment.lexicalRank }));
              return (
                <div className="fragments-panel-fragment" key={index}>
                  <p className="fragments-panel-fragment-text"><HighlightedSource text={fragment.text} highlights={fragment.highlights ?? []} /></p>
                  <p className="fragment-source">{fragment.document}</p>
                  {scoreParts.length > 0 && (
                    <p className="fragments-panel-fragment-score">{scoreParts.join(", ")}</p>
                  )}
                  <p className="fragment-filter-navigation">
                    <a href={`#${filtersId}`}>{tr("interface.fragments_jump_to_filters")}</a>
                  </p>
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
