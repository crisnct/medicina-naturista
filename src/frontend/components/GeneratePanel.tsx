import { useState } from "react";
import type { FragmentItem, GenerateMessage, ReportModel } from "../api/types";
import { MIN_SCORE_OPTIONS, reachesMinScore } from "../lib/scoreFilter";
import { TypingIndicator } from "./TypingIndicator";
import { GenerationStreamPreview } from "./GenerationStreamPreview";
import { GenerationDurationEstimate } from "./GenerationDurationEstimate";
import { DoctorAvatar } from "./DoctorAvatar";
import { AI_ACTIVITY_LABELS, type GenerationFeedback } from "../lib/generationFeedback";

export function GeneratePanel({
  message,
  fragments,
  onGenerate,
  reportModels = ["ollama-gemma4:12b", "ollama-gemma3:1b", "ollama-qwen3.5:9b", "ollama-qwen3.5:4b", "ollama-ministral-3:8b"],
  defaultReportModel,
  allowedReportModels = reportModels.filter((option) => option.startsWith("ollama-")),
  actionsDisabled = false,
  feedback,
}: {
  message: GenerateMessage;
  // The fragments of the same search; absent when that message is no longer
  // in the chat, in which case the server alone checks the threshold.
  fragments?: FragmentItem[];
  onGenerate: (searchId: string, minScore: number, model: ReportModel) => void;
  reportModels?: ReportModel[];
  defaultReportModel?: ReportModel;
  allowedReportModels?: ReportModel[];
  actionsDisabled?: boolean;
  feedback?: GenerationFeedback;
}) {
  // Only fragments whose relevance reaches this are sent to the AI (0 = all).
  const [minScore, setMinScore] = useState(0);
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
  const noModels = reportModels.length === 0;
  const modelRestricted = !noModels && !allowedReportModels.includes(selectedModel);
  const disabled = message.busy || noneReach || actionsDisabled || noModels || modelRestricted;
  const hasAnswer = Boolean(feedback?.streamPreview);
  const hasPreview = hasAnswer || Boolean(feedback?.thinkingPreview);

  return (
    <section className="generate-recipe-panel">
      <div className="generate-recipe-copy">
        <div className="chatbot-message-header">
          <DoctorAvatar />
          <h3>Pregătiți raportul</h3>
        </div>
        <p>Informațiile selectate vor fi folosite de AI pentru redactarea unui raport cu recomandări și surse.</p>
      </div>
      <div className="generate-recipe-actions">
        <div className="generation-options">
          <h4>Opțiuni de generare</h4>
          <p>Acest prag stabilește ce fragmente sunt eligibile pentru AI, independent de filtrele de afișare.</p>
          <div className="generation-model-options">
            <label className="fragments-panel-filter">
              Scor minim
              <select
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
              Model AI
              <select
                value={selectedModel}
                disabled={message.busy || actionsDisabled || noModels}
                onChange={(event) => setModel(event.target.value as ReportModel)}
              >
                {reportModels.map((option) => <option key={option} value={option}>{option}</option>)}
              </select>
            </label>
          </div>
          {modelRestricted && (
            <p className="generate-recipe-warning" role="status">
              Acest model AI poate fi accesat doar de autorul platformei.
            </p>
          )}
        </div>
        <div className="generate-report-row">
          <div className="generate-report-status">
            {noneReach && <p className="generate-recipe-warning">Niciun fragment nu atinge scorul minim selectat.</p>}
            {noModels && <p className="generate-recipe-warning">Niciun model AI disponibil pentru această sesiune.</p>}
            <p className="eligible-count">
              Fragmente eligibile pentru raport: {eligibleCount === undefined ? "numărul va fi verificat la generare" : <strong>{eligibleCount}</strong>}
            </p>
            <p className="eligible-count">
              Număr total caractere: {eligibleCharacters === undefined ? "numărul va fi verificat la generare" : <strong>{eligibleCharacters.toLocaleString("ro-RO")}</strong>}
            </p>
            <GenerationDurationEstimate
              model={selectedModel}
              characters={eligibleCharacters}
              refreshKey={feedback?.terminal ? feedback.generationId : undefined}
            />
          </div>
          <button
            type="button"
            className="generate-inline"
            disabled={disabled}
            aria-disabled={disabled}
            onClick={() => onGenerate(message.searchId, minScore, selectedModel)}
          >
            {message.busy ? "⏳ Se pregătește raportul…" : (
              <>
                <svg className="generate-report-icon" viewBox="0 0 24 24" width="28" height="28" aria-hidden="true" focusable="false">
                  <path d="M12 2H5a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7Z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
                  <path d="M12 2v5h5M7 11h6M7 15h4M7 19h4" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="m19 10 1 3 3 1-3 1-1 3-1-3-3-1 3-1Z" fill="currentColor" stroke="currentColor" strokeWidth="1" strokeLinejoin="round" />
                </svg>
                <span>Generează raportul</span>
              </>
            )}
          </button>
        </div>
      </div>
      {(message.busy || feedback?.completed || hasPreview) && (
        <div className="generation-progress-section">
          {message.busy && (
            <div className="generation-progress-row">
              <TypingIndicator
                key={feedback?.generationId ?? "pending"}
                label={feedback?.progress ?? "Pregătesc raportul. Generarea poate dura câteva minute."}
                paused={feedback?.waitingInQueue ?? true}
                startedAt={feedback?.generationStartedAt}
              />
              {feedback?.cancel && (
                <button type="button" className="secondary-button" onClick={feedback.cancel}>Anulează generarea</button>
              )}
            </div>
          )}
          <GenerationStreamPreview
            text={hasAnswer ? feedback?.streamPreview : feedback?.thinkingPreview}
            tokensPerSecond={hasAnswer ? feedback?.streamTokensPerSecond : feedback?.thinkingTokensPerSecond}
            title={hasAnswer ? "AI generează răspunsul" : "Analiza modelului AI"}
            label={hasAnswer ? "Textul primit de la AI" : "Analiza transmisă de modelul AI"}
            placeholder={feedback?.aiActivity ? AI_ACTIVITY_LABELS[feedback.aiActivity.phase] : "Aștept primul semnal de la model…"}
            activityAgeMs={message.busy ? feedback?.aiActivity?.lastActivityAgeMs : undefined}
            activityReceivedAt={feedback?.activityReceivedAt}
          />
        </div>
      )}
      {feedback?.message && !message.busy && (
        <div className="generation-feedback owner-notice-panel" role="alert">
          <div className="chatbot-message-content">
            <DoctorAvatar />
            <p className="chatbot-message-text">{feedback.message}</p>
          </div>
          {feedback.requiresAuthorization && (
            <a href={`${import.meta.env.BASE_URL}owner`} target="_blank" rel="noopener noreferrer">
              Deschide autorizarea în altă filă
            </a>
          )}
        </div>
      )}
    </section>
  );
}
