import { useEffect, useRef } from "react";
import type { ChatMessage } from "../api/types";
import { MessageBubble } from "./MessageBubble";

export function ChatHistory({
  history,
  onGenerate,
}: {
  history: ChatMessage[];
  onGenerate: (searchId: string) => void;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [history.length]);

  return (
    <div id="medical-chatbot" className="bubble-wrap">
      {history.map((message, index) => (
        <MessageBubble key={index} message={message} onGenerate={onGenerate} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
