import { useInfiniteQuery } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import type { HerbConditionsMessage } from "../api/types";
import { tr } from "../lib/texts";

type SafetyMessage = HerbConditionsMessage & { groupId: string; herbId: number; safetyRunId: string };

const groups = [
  { kind: "warning", title: "interface.herb_warnings_warning_title" },
  { kind: "contraindication", title: "interface.herb_warnings_contraindication_title" },
  { kind: "interaction", title: "interface.herb_warnings_interaction_title" },
] as const;

function WarningsList({ message }: { message: SafetyMessage }) {
  const query = useInfiniteQuery({
    queryKey: ["herb-product-safety", message.language ?? "ro", message.groupId, message.herbId, message.safetyRunId],
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) => api.getHerbSafety(message.groupId, pageParam, signal),
    getNextPageParam: (page) => page.nextOffset ?? undefined,
    staleTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  const expired = query.error instanceof ApiError && [
    "HERB_SAFETY_STALE", "HERB_SAFETY_NOT_READY", "HERB_SAFETY_UNAVAILABLE",
    "SESSION_EXPIRED", "SESSION_CLOSED",
  ].includes(query.error.code ?? "");
  const messages = expired ? [] : query.data?.pages.flatMap((page) => page.warnings) ?? [];
  return <div aria-busy={query.isFetching}>
    {query.isPending && <p role="status">{tr("interface.herb_warnings_loading")}</p>}
    {query.isError && <div role="alert">
      <p>{query.error instanceof ApiError ? query.error.message : tr("interface.herb_warnings_error")}</p>
      {!expired && <button type="button" disabled={query.isFetching} onClick={() => void (query.isFetchNextPageError ? query.fetchNextPage() : query.refetch())}>{tr("interface.herb_evidence_retry")}</button>}
    </div>}
    {messages.length > 0 && <ul className="herb-warnings-list">
      {groups.flatMap((group) => messages.filter((message) => message.kind === group.kind).map((item) => (
        <li key={item.id}><strong>{tr(group.title)}</strong>{". "}<span className="herb-warning-text">{item.text}</span></li>
      )))}
    </ul>}
    {!expired && query.hasNextPage && <button type="button" disabled={query.isFetching} onClick={() => void query.fetchNextPage()}>{tr("interface.herb_evidence_more")}</button>}
  </div>;
}

export function HerbWarningsPanel({ message }: { message: HerbConditionsMessage }) {
  const available = ["ready", "partial"].includes(message.warningsStatus ?? "") && typeof message.warningsCount === "number";
  return <section className="herb-association-section herb-warnings-section" aria-label={tr("interface.herb_warnings_title")}>
    <h4>{tr("interface.herb_warnings_title")}</h4>
    <p className="herb-association-note herb-warnings-ai-note">{tr("interface.herb_warnings_ai_note")}</p>
    {!available ? <p>{tr(message.warningsStatus === "stale" ? "interface.herb_warnings_stale" : "interface.herb_warnings_pending")}</p> : <>
      {message.warningsStatus === "partial" && <p className="herb-association-note">{tr("interface.herb_warnings_partial")}</p>}
      {message.warningsCount === 0 ? <p>{tr(message.warningsStatus === "partial" ? "interface.herb_warnings_partial_empty" : "interface.herb_warnings_empty")}</p> :
        message.groupId && message.herbId && message.safetyRunId
          ? <WarningsList message={{ ...message, groupId: message.groupId, herbId: message.herbId, safetyRunId: message.safetyRunId }} />
          : <p>{tr("interface.herb_warnings_pending")}</p>}
    </>}
  </section>;
}
