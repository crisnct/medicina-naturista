import { useId, useState, type ReactNode } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import type { HerbConditionsMessage, HerbEvidenceKind, HerbHighlight } from "../api/types";
import { tr } from "../lib/texts";

// Python offsets count Unicode code points; ordinary JS slice counts UTF-16 units.
export function HighlightedSource({ text, highlights }: { text: string; highlights: HerbHighlight[] }) {
  const points = Array.from(text);
  const result: ReactNode[] = [];
  let position = 0;
  for (const span of highlights) {
    if (span.start < position || span.end <= span.start || span.end > points.length) continue;
    result.push(points.slice(position, span.start).join(""));
    result.push(<mark key={`${span.start}-${span.end}`} className={`herb-evidence-mark-${span.kind}`}>{points.slice(span.start, span.end).join("")}</mark>);
    position = span.end;
  }
  result.push(points.slice(position).join(""));
  return <>{result}</>;
}

export function HerbEvidencePanel({ message, evidenceKind = "positive" }: { message: HerbConditionsMessage & { groupId: string }; evidenceKind?: HerbEvidenceKind }) {
  const filterId = useId();
  const [open, setOpen] = useState(false);
  const [conditionId, setConditionId] = useState<number | null>(null);
  const negative = evidenceKind === "contraindication";
  const conditions = negative ? message.contraindications ?? [] : message.conditions;
  const fragmentsCount = negative ? message.contraindicationFragmentsCount : message.fragmentsCount;
  const documentsCount = negative ? message.contraindicationDocumentsCount : message.documentsCount;
  const query = useInfiniteQuery({
    queryKey: ["herb-evidence", message.groupId, message.herbId, message.positiveRunId, conditionId, evidenceKind, message.cautionRunId],
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) => negative
      ? api.getHerbEvidence(message.groupId, conditionId, pageParam, signal, evidenceKind)
      : api.getHerbEvidence(message.groupId, conditionId, pageParam, signal),
    getNextPageParam: (page) => page.nextOffset ?? undefined,
    enabled: open,
    staleTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  const terminal = query.error instanceof ApiError && [
    "HERB_EVIDENCE_STALE", "HERB_EVIDENCE_UNAVAILABLE", "POSITIVE_RANKING_STALE", "POSITIVE_RANKING_NOT_READY", "CAUTION_RANKING_STALE", "CAUTION_RANKING_NOT_READY", "SESSION_EXPIRED", "SESSION_CLOSED",
  ].includes(query.error.code ?? "");
  const page = query.data?.pages[0];
  const fragments = terminal ? [] : query.data?.pages.flatMap((item) => item.fragments) ?? [];
  const errorMessage = query.error instanceof ApiError
    ? (["POSITIVE_RANKING_STALE", "POSITIVE_RANKING_NOT_READY"].includes(query.error.code ?? "")
      ? tr("interface.herb_evidence_stale") : query.error.message)
    : tr("interface.herb_evidence_error");

  return (
    <details className="herb-evidence-panel" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>{tr("interface.herb_evidence_summary", { fragments_count: fragmentsCount ?? 0, documents_count: documentsCount ?? 0 })}</summary>
      {open && <div className="herb-evidence-content" aria-busy={query.isFetching}>
        <div className="herb-evidence-toolbar">
          <label htmlFor={filterId}>{tr("interface.herb_evidence_filter")}
            <select id={filterId} value={conditionId ?? "all"} onChange={(event) => setConditionId(event.target.value === "all" ? null : Number(event.target.value))}>
              <option value="all">{tr("common.all")}</option>
              {conditions.map((condition) => <option key={condition.id} value={condition.id}>{condition.name}</option>)}
            </select>
          </label>
          <div className="herb-evidence-legend" aria-label={tr("interface.herb_evidence_legend")}>
            <span><mark className="herb-evidence-mark-herb">{tr("interface.herb_evidence_herb_legend")}</mark></span>
            <span><mark className="herb-evidence-mark-condition">{tr("interface.herb_evidence_condition_legend")}</mark></span>
          </div>
        </div>
        {query.isPending && <p role="status">{tr("interface.herb_evidence_loading")}</p>}
        {query.isError && <div role="alert">
          <p>{errorMessage}</p>
          {!terminal && <button type="button" disabled={query.isFetching} onClick={() => void (query.isFetchNextPageError ? query.fetchNextPage() : query.refetch())}>{tr("interface.herb_evidence_retry")}</button>}
        </div>}
        {!terminal && fragments.map((fragment) => <article className="herb-evidence-fragment" key={fragment.chunkId}>
          <p className="herb-evidence-associations">{tr(negative ? "interface.herb_evidence_prohibitions" : "interface.herb_evidence_conditions", { conditions: fragment.conditions.map((condition) => condition.name).join(" · ") })}</p>
          {fragment.heading && <h5><HighlightedSource text={fragment.heading} highlights={fragment.headingHighlights} /></h5>}
          <p className="herb-evidence-text"><HighlightedSource text={fragment.text} highlights={fragment.textHighlights} /></p>
          <p className="fragment-source">{tr("interface.herb_evidence_source", { document: fragment.document, line_start: fragment.lineStart, line_end: fragment.lineEnd })}</p>
        </article>)}
        {!terminal && page && <>
          {fragments.length === 0 && <p>{tr("interface.herb_evidence_empty")}</p>}
          <p className="herb-evidence-count" role="status">{tr("interface.herb_evidence_shown", { visible_count: fragments.length, total_count: page.fragmentsCount, document_count: page.documentsCount })}</p>
          {query.hasNextPage && !query.isError && <button type="button" disabled={query.isFetching} onClick={() => void query.fetchNextPage()}>{query.isFetchingNextPage ? tr("interface.herb_evidence_loading") : tr("interface.herb_evidence_more")}</button>}
        </>}
      </div>}
    </details>
  );
}
