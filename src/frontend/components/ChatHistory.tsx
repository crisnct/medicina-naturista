import { useMemo } from "react";
import type { ChatMessage, FragmentItem, ReportModel } from "../api/types";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";
import type { GenerationFeedback } from "../lib/generationFeedback";

export function ChatHistory({
  history,
  pending,
  pendingLabel,
  onGenerate,
  reportModels,
  defaultReportModel,
  actionsDisabled,
  generationFeedback,
}: {
  history: ChatMessage[];
  pending: boolean;
  pendingLabel?: string;
  onGenerate: (searchId: string, minScore: number, model: ReportModel) => void;
  reportModels?: ReportModel[];
  defaultReportModel?: ReportModel;
  actionsDisabled?: boolean;
  generationFeedback?: Record<string, GenerationFeedback>;
}) {
  // Each search's fragments, so its "Generează raportul" section can tell how
  // many of them reach the "Scor minim" chosen there.
  const fragmentsBySearch = useMemo(() => {
    const bySearch = new Map<string, FragmentItem[]>();
    for (const message of history) {
      if (message.kind === "fragments") bySearch.set(message.searchId, message.fragments);
    }
    return bySearch;
  }, [history]);

  // Restore persisted generation failures after a session reload, in the same
  // red panel used for live failures rather than as a second chat message.
  const persistedFeedback = useMemo(() => {
    const bySearch = new Map<string, GenerationFeedback>();
    for (const message of history) {
      if (message.kind === "text" && message.generationSearchId) {
        bySearch.set(message.generationSearchId, { message: message.content });
      }
    }
    return bySearch;
  }, [history]);

  return (
    <div
      id="medical-chatbot"
      className="bubble-wrap"
      role="log"
      aria-label="Conversație"
    >
      {history.filter((message) => !(message.kind === "text" && message.generationSearchId)).map((message, index) => (
        <MessageBubble
          key={index}
          message={message}
          fragments={message.kind === "generate" ? fragmentsBySearch.get(message.searchId) : undefined}
          onGenerate={onGenerate}
          reportModels={reportModels}
          defaultReportModel={defaultReportModel}
          actionsDisabled={actionsDisabled}
          generationFeedback={message.kind === "generate" ? generationFeedback?.[message.searchId] ?? persistedFeedback.get(message.searchId) : undefined}
        />
      ))}
      {pending && <TypingIndicator label={pendingLabel} />}
    </div>
  );
}
