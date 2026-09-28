import type { ChatMessage } from "../api/types";
import { renderRecommendationText } from "../lib/inlineMarkdown";
import { FragmentsPanel } from "./FragmentsPanel";
import { GeneratePanel } from "./GeneratePanel";
import { DownloadPanel } from "./DownloadPanel";

export function MessageBubble({
  message,
  onGenerate,
}: {
  message: ChatMessage;
  onGenerate: (searchId: string) => void;
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
          <GeneratePanel message={message} onGenerate={onGenerate} />
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
