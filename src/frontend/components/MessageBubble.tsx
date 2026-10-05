import type { ChatMessage, FragmentItem } from "../api/types";
import { renderRecommendationText } from "../lib/inlineMarkdown";
import { FragmentsPanel } from "./FragmentsPanel";
import { GeneratePanel } from "./GeneratePanel";
import { DownloadPanel } from "./DownloadPanel";

export function MessageBubble({
  message,
  fragments,
  onGenerate,
}: {
  message: ChatMessage;
  // For a "generate" message: the fragments of the same search, when still in the chat.
  fragments?: FragmentItem[];
  onGenerate: (searchId: string, minScore: number) => void;
}) {
  switch (message.kind) {
    case "fragments":
      return (
        <div className="message-wrap bot unwrapped">
          <FragmentsPanel message={message} />
        </div>
      );
    case "generate":
      return (
        <div className="message-wrap bot unwrapped">
          <GeneratePanel message={message} fragments={fragments} onGenerate={onGenerate} />
        </div>
      );
    case "download":
      return (
        <div className="message-wrap bot unwrapped">
          <DownloadPanel message={message} />
        </div>
      );
    case "text":
    default:
      return (
        <div className={`message-wrap ${message.role}`}>
          <div className="message">{renderRecommendationText(message.content)}</div>
        </div>
      );
  }
}
