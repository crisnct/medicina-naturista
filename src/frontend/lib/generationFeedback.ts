import { tr } from "./texts";
import type { AIActivity } from "../api/types";

export const AI_ACTIVITY_LABELS: Record<AIActivity["phase"], string> = {
  waiting: tr("common.waiting_for_model"),
  processing: tr("interface.activity_processing"),
  thinking: tr("interface.activity_thinking"),
  answering: tr("interface.activity_answering"),
};

export interface GenerationFeedback {
  message: string;
  requiresAuthorization?: boolean;
  progress?: string;
  generationId?: string;
  generationStartedAt?: number | null;
  waitingInQueue?: boolean;
  streamPreview?: string | null;
  reportPreview?: string | null;
  batchesCompleted?: number;
  batchesTotal?: number;
  streamTokensPerSecond?: number | null;
  thinkingTokensPerSecond?: number | null;
  completed?: boolean;
  terminal?: boolean;
  thinkingPreview?: string | null;
  aiActivity?: AIActivity | null;
  activityReceivedAt?: number;
  cancel?: () => void;
}
