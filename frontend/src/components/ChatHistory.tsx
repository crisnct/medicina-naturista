import { useEffect, useRef } from "react";
import type { ChatMessage } from "../api/types";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";

export function ChatHistory({
  history,
  pending,
  onGenerate,
}: {
  history: ChatMessage[];
  pending: boolean;
  onGenerate: (searchId: string) => void;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [history.length, pending]);

  return (
    <div id="medical-chatbot" className="bubble-wrap">
      {history.map((message, index) => (
        <MessageBubble key={index} message={message} onGenerate={onGenerate} />
      ))}
      {pending && <TypingIndicator />}
      <div ref={bottomRef} />
    </div>
  );
}
