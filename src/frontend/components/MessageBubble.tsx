import type { ChatMessage, FragmentItem, ReportEffort, ReportModel } from "../api/types";
import { renderRecommendationText } from "../lib/inlineMarkdown";
import { FragmentsPanel } from "./FragmentsPanel";
import { GeneratePanel } from "./GeneratePanel";
import { DownloadPanel } from "./DownloadPanel";
import { HerbConditionsPanel } from "./HerbConditionsPanel";
import { DoctorAvatar } from "./DoctorAvatar";
import type { GenerationFeedback } from "../lib/generationFeedback";

export function MessageBubble({
  message,
  fragments,
  onGenerate,
  reportModels,
  defaultReportModel,
  allowedReportModels,
  effortReportModels,
  actionsDisabled,
  generationFeedback,
}: {
  message: ChatMessage;
  // For a "generate" message: the fragments of the same search, when still in the chat.
  fragments?: FragmentItem[];
  onGenerate: (searchId: string, minScore: number, model: ReportModel, effort: ReportEffort) => void;
  reportModels?: ReportModel[];
  defaultReportModel?: ReportModel;
  allowedReportModels?: ReportModel[];
  effortReportModels?: ReportModel[];
  actionsDisabled?: boolean;
  generationFeedback?: GenerationFeedback;
}) {
  switch (message.kind) {
    case "herb_conditions":
      return <div className="message-wrap bot unwrapped"><HerbConditionsPanel message={message} /></div>;
    case "fragments":
      return (
        <div className="message-wrap bot unwrapped">
          <FragmentsPanel message={message} />
        </div>
      );
    case "generate":
      return (
        <div className="message-wrap bot unwrapped">
          <GeneratePanel message={message} fragments={fragments} onGenerate={onGenerate} reportModels={reportModels} defaultReportModel={defaultReportModel} allowedReportModels={allowedReportModels} effortReportModels={effortReportModels} actionsDisabled={actionsDisabled} feedback={generationFeedback} />
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
        <div className={`message-wrap ${message.role}${message.groupId === "greeting" ? " welcome-message" : ""}`}>
          <div className="message">
            {message.role === "assistant" ? (
              <div className="chatbot-message-content">
                <DoctorAvatar />
                <div className="chatbot-message-text">{renderRecommendationText(message.content)}</div>
              </div>
            ) : renderRecommendationText(message.content)}
          </div>
        </div>
      );
  }
}
