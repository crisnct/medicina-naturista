import { useMemo } from "react";
import type { ChatMessage, FragmentItem } from "../api/types";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";

export function ChatHistory({
  history,
  pending,
  pendingLabel,
  onGenerate,
}: {
  history: ChatMessage[];
  pending: boolean;
  pendingLabel?: string;
  onGenerate: (searchId: string, minScore: number) => void;
}) {
  // Each search's fragments, so its "Generează rețeta" section can tell how
  // many of them reach the "Scor minim" chosen there.
  const fragmentsBySearch = useMemo(() => {
    const bySearch = new Map<string, FragmentItem[]>();
    for (const message of history) {
      if (message.kind === "fragments") bySearch.set(message.searchId, message.fragments);
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
      {history.map((message, index) => (
        <MessageBubble
          key={index}
          message={message}
          fragments={message.kind === "generate" ? fragmentsBySearch.get(message.searchId) : undefined}
          onGenerate={onGenerate}
        />
      ))}
      {pending && <TypingIndicator label={pendingLabel} />}
    </div>
  );
}
