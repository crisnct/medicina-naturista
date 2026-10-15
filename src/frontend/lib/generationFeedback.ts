import type { AIActivity } from "../api/types";

export const AI_ACTIVITY_LABELS: Record<AIActivity["phase"], string> = {
  waiting: "Aștept primul semnal de la model…",
  processing: "Furnizorul AI a confirmat cererea…",
  thinking: "Modelul analizează informațiile…",
  answering: "Modelul redactează raportul…",
};

export interface GenerationFeedback {
  message: string;
  requiresAuthorization?: boolean;
  progress?: string;
  generationId?: string;
  generationStartedAt?: number | null;
  waitingInQueue?: boolean;
  streamPreview?: string | null;
  streamTokensPerSecond?: number | null;
  thinkingTokensPerSecond?: number | null;
  completed?: boolean;
  terminal?: boolean;
  thinkingPreview?: string | null;
  aiActivity?: AIActivity | null;
  activityReceivedAt?: number;
  cancel?: () => void;
}
