import type { ChatMessage, ResourceInvalidations } from "../api/types";

export function reconcileRetention(history: ChatMessage[], result: ResourceInvalidations): ChatMessage[] {
  const groups = new Set(result.evictedGroupIds ?? []);
  const searches = new Set(result.evictedSearchIds ?? []);
  const reports = new Set(result.evictedReportIds ?? []);
  return history.filter((message) =>
    !(message.groupId && groups.has(message.groupId)) &&
    !((message.kind === "fragments" || message.kind === "generate") && searches.has(message.searchId)) &&
    !(message.kind === "download" && reports.has(message.reportId)),
  );
}
