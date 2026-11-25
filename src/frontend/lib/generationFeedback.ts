import { tr } from "./texts";
import type { AIActivity, ReportBatchPreview, ResourceCheck, ResourceDecision } from "../api/types";

export const AI_ACTIVITY_LABELS: Record<AIActivity["phase"], string> = {
  get waiting() { return tr("common.waiting_for_model"); },
  get processing() { return tr("interface.activity_processing"); },
  get thinking() { return tr("interface.activity_thinking"); },
  get answering() { return tr("interface.activity_answering"); },
};

// The job stages during which a local model changes hands on the graphics card; the two resource
// stages belong to Colibri, which measures the memory first and may ask the user.
export type ModelStage = "stopping_model" | "checking_resources" | "awaiting_resources" | "warming_model";
export const MODEL_STAGES: readonly string[] = ["stopping_model", "checking_resources", "awaiting_resources", "warming_model"];

export interface GenerationFeedback {
  message: string;
  modelStage?: ModelStage;
  modelName?: string;
  requiresAuthorization?: boolean;
  progress?: string;
  generationId?: string;
  generationStartedAt?: number | null;
  waitingInQueue?: boolean;
  streamPreview?: string | null;
  reportPreview?: string | null;
  batchesCompleted?: number;
  batchesTotal?: number;
  batchPreviews?: ReportBatchPreview[];
  streamTokensPerSecond?: number | null;
  thinkingTokensPerSecond?: number | null;
  completed?: boolean;
  terminal?: boolean;
  thinkingPreview?: string | null;
  aiActivity?: AIActivity | null;
  activityReceivedAt?: number;
  cancel?: () => void;
  resourceCheck?: ResourceCheck | null;
  decideResources?: (decision: ResourceDecision) => void;
  decisionPending?: boolean;
}
