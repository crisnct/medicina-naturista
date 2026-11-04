import { getLanguage, locale, tr } from "../lib/texts";
import { useLayoutEffect, useRef, useState } from "react";
import { REPORT_EFFORTS, type FragmentItem, type GenerateMessage, type GenerationLimitDefaults, type GenerationLimits, type ReportEffort, type ReportModel, type ReportModelDetails } from "../api/types";
import { useMinScore } from "../hooks/useMinScore";
import { useOutputRecommendation } from "../hooks/useOutputRecommendation";
import { MIN_SCORE_OPTIONS, reachesMinScore } from "../lib/scoreFilter";
import { checkLimits } from "../lib/generationLimits";
import { TypingIndicator } from "./TypingIndicator";
import { GenerationStreamPreview } from "./GenerationStreamPreview";
import { GenerationReportPreview } from "./GenerationReportPreview";
import { GenerationBatchEstimate } from "./GenerationBatchEstimate";
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
  "vllm-qwen3.5:4b": "interface.model_vllm_qwen35_4b",
  "deepseek-flash": "interface.model_deepseek_flash",
  "huggingface-deepseek-v4-flash": "interface.model_huggingface_deepseek_flash",
  "grok-4.3": "interface.model_grok43",
} as const satisfies Record<ReportModel, string>;

const EFFORT_LABELS = {
  low: "interface.effort_low",
  medium: "interface.effort_medium",
  high: "interface.effort_high",
} as const satisfies Record<ReportEffort, string>;

const TOKEN_LABELS = {
  batchMaxTokens: "interface.generate_batch_tokens_label",
  maxOutputTokens: "interface.generate_output_tokens_label",
  thinkingTokens: "interface.generate_thinking_tokens_label",
} as const;
type TokenField = keyof typeof TOKEN_LABELS;
const TOKEN_FIELDS = Object.keys(TOKEN_LABELS) as TokenField[];

export function GeneratePanel({
  message,
  fragments,
  onGenerate,
  reportModels = ["ollama-gemma4:12b", "ollama-gemma3:1b", "ollama-qwen3.5:9b", "ollama-qwen3.5:4b", "ollama-ministral-3:8b", "ollama-deepseek-r1:8b"],
  defaultReportModel,
  allowedReportModels = [],
  effortReportModels = [],
  generationLimitDefaults,
  reportModelDetails,
  actionsDisabled = false,
  feedback,
}: {
  message: GenerateMessage;
  // The fragments of the same search; absent when that message is no longer
  // in the chat, in which case the server alone checks the threshold.
  fragments?: FragmentItem[];
  onGenerate: (searchId: string, minScore: number, model: ReportModel, effort: ReportEffort, limits?: GenerationLimits) => void;
  reportModels?: ReportModel[];
  defaultReportModel?: ReportModel;
  allowedReportModels?: ReportModel[];
  // Models that accept an effort; the selector is disabled for the others.
  effortReportModels?: ReportModel[];
  // The configured generation limits; the server sends them to the admin only.
  generationLimitDefaults?: GenerationLimitDefaults;
  // Per-model context window and starting effort, sent to everyone.
  reportModelDetails?: ReportModelDetails;
  actionsDisabled?: boolean;
  feedback?: GenerationFeedback;
}) {
  // Only fragments whose relevance reaches this are sent to the AI (0 = all).
  const [minScore, setMinScore] = useMinScore(message.searchId);
  // The score also filters the fragments above, changing their height; the conversation
  // card has no scroll anchoring, so keep this selector where the user clicked it.
  const minScoreSelect = useRef<HTMLSelectElement>(null);
  const minScoreSelectTop = useRef<number | null>(null);
  useLayoutEffect(() => {
    if (minScoreSelectTop.current === null || !minScoreSelect.current) return;
    const shift = minScoreSelect.current.getBoundingClientRect().top - minScoreSelectTop.current;
    minScoreSelectTop.current = null;
    if (shift) window.scrollBy({ top: shift, behavior: "instant" });
  }, [minScore]);
  // A chosen effort belongs to the model it was chosen for; another model starts at its configured one.
  const [typedEffort, setTypedEffort] = useState<{ model: ReportModel; value: ReportEffort } | null>(null);
  const [model, setModel] = useState<ReportModel | null>(null);
  // An edited token field belongs to the model it was typed for, so choosing
  // another model shows that model's configured value again.
  const [typedTokens, setTypedTokens] = useState<Partial<Record<TokenField, { model: ReportModel; value: string }>>>({});
  const [typedWorkers, setTypedWorkers] = useState<string | null>(null);
  const preferredModel = model ?? defaultReportModel ?? reportModels[0];
  const selectedModel = reportModels.includes(preferredModel)
    ? preferredModel : reportModels[0] ?? "ollama-gemma4:12b";
  const effort = typedEffort?.model === selectedModel
    ? typedEffort.value : reportModelDetails?.defaultEfforts[selectedModel] ?? "low";
  const contextTokens = reportModelDetails?.contextTokens[selectedModel];
  const effortSupported = effortReportModels.includes(selectedModel);
  // Only the admin sees the limits, so only then is a recommendation needed.
  const recommendation = useOutputRecommendation(
    selectedModel,
    effortSupported ? effort : undefined,
    generationLimitDefaults !== undefined && allowedReportModels.includes(selectedModel),
    feedback?.terminal ? feedback.generationId : undefined,
  );
  const recommendedTokens = recommendation?.tokens;
  const tokenValue = (field: TokenField) => {
    const typed = typedTokens[field];
    const configured = generationLimitDefaults?.[field][selectedModel];
    // A measured need above the configured limit becomes the starting value.
    const start = field === "maxOutputTokens" && configured !== undefined && recommendedTokens !== undefined
      ? Math.max(configured, recommendedTokens) : configured;
    return typed?.model === selectedModel ? typed.value : String(start ?? "");
  };
  const workersText = typedWorkers ?? "0";
  const maxWorkers = generationLimitDefaults?.batchWorkers.max ?? 0;
  const workers = /^\d{1,4}$/.test(workersText.trim()) && Number(workersText) <= maxWorkers ? Number(workersText) : null;
  // One request may use only part of the context while batches run in parallel (0 and 1 = in succession).
  const requestContext = workers !== null && workers <= 1 ? contextTokens : reportModelDetails?.parallelContextTokens[selectedModel] ?? contextTokens;
  // The thinking budget matters only while the chosen effort lets the model think.
  const thinkingShown = effortSupported && effort !== "low";
  const shownTokenFields = TOKEN_FIELDS.filter((field) => field !== "thinkingTokens" || thinkingShown);
  const limitsCheck = generationLimitDefaults && checkLimits(
    tokenValue("batchMaxTokens"),
    tokenValue("maxOutputTokens"),
    generationLimitDefaults.tokenBounds,
    requestContext,
    thinkingShown ? tokenValue("thinkingTokens") : undefined,
  );
  const tokensValid = (limitsCheck?.valid ?? true) && workers !== null;
  // Below what reports of this model and effort have needed, the answer is likely to be cut off.
  const belowRecommended = recommendedTokens !== undefined && limitsCheck?.limits !== undefined
    && limitsCheck.limits.maxOutputTokens < recommendedTokens;
  const fieldError = (field: TokenField) => ({
    batchMaxTokens: limitsCheck?.inputError,
    maxOutputTokens: limitsCheck?.outputError,
    thinkingTokens: limitsCheck?.thinkingError,
  })[field];
  const eligibleFragments = fragments?.filter((fragment) => reachesMinScore(fragment.relevancePercent, minScore));
  const eligibleCount = eligibleFragments?.length;
  const eligibleCharacters = eligibleFragments?.reduce(
    (sum, fragment) => sum + (fragment.charactersCount ?? Array.from(fragment.text).length),
    0,
  );
  const noneReach = eligibleCount === 0;
  const noModels = reportModels.length === 0;
  const modelRestricted = !noModels && !allowedReportModels.includes(selectedModel);
  // Admin only: hidden while the model is not permitted or the server sent no limits.
  const showLimits = generationLimitDefaults !== undefined && !noModels && !modelRestricted;
  const disabled = message.busy || noneReach || actionsDisabled || noModels || modelRestricted
    || (showLimits && (!tokensValid || belowRecommended));
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
                ref={minScoreSelect}
                value={minScore}
                disabled={message.busy || actionsDisabled}
                onChange={(event) => {
                  minScoreSelectTop.current = event.currentTarget.getBoundingClientRect().top;
                  setMinScore(Number(event.target.value));
                }}
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
              {contextTokens !== undefined && (
                <small className="generation-model-context">{tr("interface.generate_model_context", { tokens: contextTokens.toLocaleString(locale()) })}</small>
              )}
              {!effortSupported && !noModels && (
                <small className="generation-effort-hint">{tr("interface.effort_unsupported_hint")}</small>
              )}
            </label>
            <label className="fragments-panel-filter">
              {tr("interface.generate_effort_label")}<select
                value={effort}
                disabled={message.busy || actionsDisabled || noModels || !effortSupported}
                onChange={(event) => setTypedEffort({ model: selectedModel, value: event.target.value as ReportEffort })}
              >
                {REPORT_EFFORTS.map((option) => <option key={option} value={option}>{tr(EFFORT_LABELS[option])}</option>)}
              </select>
            </label>
            {showLimits && (
              <label className="fragments-panel-filter">
                {tr("interface.generate_batch_workers_label")}<input
                  type="text"
                  inputMode="numeric"
                  value={workersText}
                  disabled={message.busy || actionsDisabled}
                  aria-invalid={workers === null}
                  onChange={(event) => setTypedWorkers(event.target.value)}
                />
              </label>
            )}
            {showLimits && shownTokenFields.map((field) => (
              <label key={field} className="fragments-panel-filter">
                {tr(TOKEN_LABELS[field])}<input
                  type="text"
                  inputMode="numeric"
                  value={tokenValue(field)}
                  disabled={message.busy || actionsDisabled}
                  aria-invalid={fieldError(field) !== undefined}
                  onChange={(event) => setTypedTokens((old) => ({ ...old, [field]: { model: selectedModel, value: event.target.value } }))}
                />
              </label>
            ))}
          </div>
          {showLimits && workers === null && (
            <p className="generate-recipe-warning" role="status">{tr("interface.generate_batch_workers_invalid", { maximum: maxWorkers })}</p>
          )}
          {showLimits && shownTokenFields.map((field) => fieldError(field) && (
            <p key={field} className="generate-recipe-warning" role="status">{fieldError(field)}</p>
          ))}
          {showLimits && thinkingShown && (
            <p className="eligible-count" role="status">{tr("interface.generate_thinking_note")}</p>
          )}
          {showLimits && recommendation && recommendedTokens !== undefined && (
            <p className={belowRecommended ? "generate-recipe-warning" : "eligible-count"} role="status">
              {belowRecommended
                ? tr("interface.generate_output_below_recommended", { tokens: recommendedTokens.toLocaleString(locale()) })
                : tr("interface.generate_output_recommended", { tokens: recommendedTokens.toLocaleString(locale()), count: recommendation.sampleCount })}
            </p>
          )}
          {showLimits && limitsCheck?.notes.map((note) => (
            <p key={note.text} className={note.warning ? "generate-recipe-warning" : "eligible-count"} role="status">{note.text}</p>
          ))}
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
            <GenerationBatchEstimate
              searchId={message.searchId}
              minScore={minScore}
              model={selectedModel}
              effort={effortSupported ? effort : undefined}
              limits={showLimits && limitsCheck?.limits && workers !== null ? { ...limitsCheck.limits, batchWorkers: workers } : undefined}
              eligibleCount={eligibleCount}
              valid={!showLimits || tokensValid}
            />
          </div>
          <button
            type="button"
            className={`generate-inline${message.busy ? " is-preparing" : ""}`}
            disabled={disabled}
            aria-disabled={disabled}
            onClick={() => {
              const limits = showLimits ? limitsCheck?.limits : undefined;
              if (!limits || workers === null) return onGenerate(message.searchId, minScore, selectedModel, effort);
              onGenerate(message.searchId, minScore, selectedModel, effort, { ...limits, batchWorkers: workers });
            }}
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
