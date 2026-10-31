import { getLanguage, locale, tr } from "../lib/texts";
import { useState } from "react";
import { REPORT_EFFORTS, type FragmentItem, type GenerateMessage, type ReportEffort, type ReportModel } from "../api/types";
import { MIN_SCORE_OPTIONS, reachesMinScore } from "../lib/scoreFilter";
import { TypingIndicator } from "./TypingIndicator";
import { GenerationStreamPreview } from "./GenerationStreamPreview";
import { GenerationReportPreview } from "./GenerationReportPreview";
import { GenerationDurationEstimate } from "./GenerationDurationEstimate";
import { DoctorAvatar } from "./DoctorAvatar";
import { AI_ACTIVITY_LABELS, type GenerationFeedback } from "../lib/generationFeedback";

// Display names are editable; provider routing continues to use the original IDs.
const MODEL_LABELS = {
  "ollama-gemma4:12b": "interface.model_gemma4",
  "ollama-gemma3:1b": "interface.model_gemma3",
  "ollama-qwen3.5:9b": "interface.model_qwen35_9b",
  "ollama-qwen3.5:4b": "interface.model_qwen35_4b",
  "ollama-ministral-3:8b": "interface.model_ministral3",
  "ollama-deepseek-r1:8b": "interface.model_deepseek_r1",
  "deepseek-flash": "interface.model_deepseek_flash",
  "huggingface-deepseek-v4-flash": "interface.model_huggingface_deepseek_flash",
  "grok-4.3": "interface.model_grok43",
} as const satisfies Record<ReportModel, string>;

const EFFORT_LABELS = {
  low: "interface.effort_low",
  medium: "interface.effort_medium",
  high: "interface.effort_high",
} as const satisfies Record<ReportEffort, string>;

export function GeneratePanel({
  message,
  fragments,
  onGenerate,
  reportModels = ["ollama-gemma4:12b", "ollama-gemma3:1b", "ollama-qwen3.5:9b", "ollama-qwen3.5:4b", "ollama-ministral-3:8b", "ollama-deepseek-r1:8b"],
  defaultReportModel,
  allowedReportModels = [],
  effortReportModels = [],
  actionsDisabled = false,
  feedback,
}: {
  message: GenerateMessage;
  // The fragments of the same search; absent when that message is no longer
  // in the chat, in which case the server alone checks the threshold.
  fragments?: FragmentItem[];
  onGenerate: (searchId: string, minScore: number, model: ReportModel, effort: ReportEffort) => void;
  reportModels?: ReportModel[];
  defaultReportModel?: ReportModel;
  allowedReportModels?: ReportModel[];
  // Models that accept an effort; the selector is disabled for the others.
  effortReportModels?: ReportModel[];
  actionsDisabled?: boolean;
  feedback?: GenerationFeedback;
}) {
  // Only fragments whose relevance reaches this are sent to the AI (0 = all).
  const [minScore, setMinScore] = useState(0);
  const [effort, setEffort] = useState<ReportEffort>("low");
  const [model, setModel] = useState<ReportModel | null>(null);
  const preferredModel = model ?? defaultReportModel ?? reportModels[0];
  const selectedModel = reportModels.includes(preferredModel)
    ? preferredModel : reportModels[0] ?? "ollama-gemma4:12b";
  const eligibleFragments = fragments?.filter((fragment) => reachesMinScore(fragment.relevancePercent, minScore));
  const eligibleCount = eligibleFragments?.length;
  const eligibleCharacters = eligibleFragments?.reduce(
    (sum, fragment) => sum + (fragment.charactersCount ?? Array.from(fragment.text).length),
    0,
  );
  const noneReach = eligibleCount === 0;
  const effortSupported = effortReportModels.includes(selectedModel);
  const noModels = reportModels.length === 0;
  const modelRestricted = !noModels && !allowedReportModels.includes(selectedModel);
  const disabled = message.busy || noneReach || actionsDisabled || noModels || modelRestricted;
  const hasAnswer = Boolean(feedback?.streamPreview);
  const batched = feedback?.batchesTotal !== undefined || (!hasAnswer && !feedback?.thinkingPreview);
  const hasPreview = Boolean(feedback?.reportPreview) || hasAnswer || Boolean(feedback?.thinkingPreview);
  const hasBatchPlan = (feedback?.batchesTotal ?? 0) > 0;

  return (
    <section className="generate-recipe-panel">
      <div className="generate-recipe-copy">
        <div className="chatbot-message-header">
          <DoctorAvatar />
          <h3>{tr("interface.generate_title")}</h3>
        </div>
        <p>{tr("interface.generate_description")}</p>
      </div>
      <div className="generate-recipe-actions">
        <div className="generation-options">
          <h4>{tr("interface.generate_options_title")}</h4>
          <div className="generation-model-options">
            <label className="fragments-panel-filter">
              {tr("common.minimum_score")}<select
                value={minScore}
                disabled={message.busy || actionsDisabled}
                onChange={(event) => setMinScore(Number(event.target.value))}
              >
                {MIN_SCORE_OPTIONS.map(({ value, label }) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="fragments-panel-filter">
              {tr("interface.generate_model_label")}<select
                value={selectedModel}
                disabled={message.busy || actionsDisabled || noModels}
                onChange={(event) => setModel(event.target.value as ReportModel)}
              >
                {reportModels.map((option) => <option key={option} value={option}>{tr(MODEL_LABELS[option])}</option>)}
              </select>
            </label>
            <label className="fragments-panel-filter" title={effortSupported ? undefined : tr("interface.effort_unsupported_hint")}>
              {tr("interface.generate_effort_label")}<select
                value={effort}
                disabled={message.busy || actionsDisabled || noModels || !effortSupported}
                onChange={(event) => setEffort(event.target.value as ReportEffort)}
              >
                {REPORT_EFFORTS.map((option) => <option key={option} value={option}>{tr(EFFORT_LABELS[option])}</option>)}
              </select>
            </label>
          </div>
          {!effortSupported && !noModels && (
            <p className="eligible-count">{tr("interface.effort_unsupported_hint")}</p>
          )}
          {modelRestricted && (
            <p className="generate-recipe-warning" role="status">
              {tr("common.owner_only_generation")}</p>
          )}
        </div>
        <div className="generate-report-row">
          <div className="generate-report-status">
            {noneReach && <p className="generate-recipe-warning">{tr("interface.generate_no_eligible_fragments")}</p>}
            {noModels && <p className="generate-recipe-warning">{tr("interface.generate_no_models")}</p>}
            <p className="eligible-count">
              {tr("interface.generate_eligible_fragments_prefix")}{eligibleCount === undefined ? tr("interface.generate_count_pending") : <strong>{eligibleCount}</strong>}
            </p>
            <p className="eligible-count">
              {tr("interface.generate_characters_prefix")}{eligibleCharacters === undefined ? tr("interface.generate_count_pending") : <strong>{eligibleCharacters.toLocaleString(locale())}</strong>}
            </p>
            <GenerationDurationEstimate
              model={selectedModel}
              effort={effortSupported ? effort : undefined}
              characters={eligibleCharacters}
              refreshKey={feedback?.terminal ? feedback.generationId : undefined}
            />
          </div>
          <button
            type="button"
            className={`generate-inline${message.busy ? " is-preparing" : ""}`}
            disabled={disabled}
            aria-disabled={disabled}
            onClick={() => onGenerate(message.searchId, minScore, selectedModel, effort)}
          >
            {message.busy ? tr("interface.generate_preparing") : (
              <>
                <svg className="generate-report-icon" viewBox="0 0 24 24" width="28" height="28" aria-hidden="true" focusable="false">
                  <path d="M12 2H5a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7Z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
                  <path d="M12 2v5h5M7 11h6M7 15h4M7 19h4" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="m19 10 1 3 3 1-3 1-1 3-1-3-3-1 3-1Z" fill="currentColor" stroke="currentColor" strokeWidth="1" strokeLinejoin="round" />
                </svg>
                <span>{tr("interface.generate_submit")}</span>
              </>
            )}
          </button>
        </div>
      </div>
      {(message.busy || feedback?.completed || hasPreview || hasBatchPlan) && (
        <div className="generation-progress-section">
          {message.busy && (
            <div className="generation-progress-row">
              <TypingIndicator
                key={feedback?.generationId ?? "pending"}
                label={feedback?.progress ?? tr("interface.generate_wait_notice")}
                paused={feedback?.waitingInQueue ?? true}
                startedAt={feedback?.generationStartedAt}
              />
              {feedback?.cancel && (
                <button type="button" className="secondary-button" onClick={feedback.cancel}>{tr("interface.generate_cancel")}</button>
              )}
            </div>
          )}
          {batched ? <GenerationReportPreview
            text={feedback?.reportPreview}
            completed={feedback?.batchesCompleted}
            total={feedback?.batchesTotal}
            batches={feedback?.batchPreviews}
            terminal={feedback?.terminal}
            succeeded={feedback?.completed}
            waitingInQueue={feedback?.waitingInQueue}
            tokensPerSecond={feedback?.streamTokensPerSecond ?? feedback?.thinkingTokensPerSecond}
            activityAgeMs={message.busy ? feedback?.aiActivity?.lastActivityAgeMs : undefined}
            activityReceivedAt={feedback?.activityReceivedAt}
            answer={feedback?.completed ? undefined : feedback?.streamPreview}
            thinking={feedback?.completed ? undefined : feedback?.thinkingPreview}
            pendingLabel={feedback?.aiActivity ? AI_ACTIVITY_LABELS[feedback.aiActivity.phase] : undefined}
          /> : <GenerationStreamPreview
            text={hasAnswer ? feedback?.streamPreview : feedback?.thinkingPreview}
            tokensPerSecond={hasAnswer ? feedback?.streamTokensPerSecond : feedback?.thinkingTokensPerSecond}
            title={hasAnswer ? tr("common.ai_answer_title") : tr("interface.generate_analysis_title")}
            label={hasAnswer ? tr("interface.generate_answer_label") : tr("interface.generate_analysis_label")}
            placeholder={feedback?.aiActivity ? AI_ACTIVITY_LABELS[feedback.aiActivity.phase] : tr("common.waiting_for_model")}
            activityAgeMs={message.busy ? feedback?.aiActivity?.lastActivityAgeMs : undefined}
            activityReceivedAt={feedback?.activityReceivedAt}
          />}
        </div>
      )}
      {feedback?.message && !message.busy && (
        <div className="generation-feedback owner-notice-panel" role="alert">
          <div className="chatbot-message-content">
            <DoctorAvatar />
            <p className="chatbot-message-text">{feedback.message}</p>
          </div>
          {feedback.requiresAuthorization && (
            <a href={`${import.meta.env.BASE_URL}owner?language=${getLanguage()}`} target="_blank" rel="noopener noreferrer">
              {tr("interface.generate_open_authorization")}</a>
          )}
        </div>
      )}
    </section>
  );
}
