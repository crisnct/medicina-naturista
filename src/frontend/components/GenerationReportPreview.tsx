import { tr } from "../lib/texts";
import { useEffect, useRef } from "react";
import { renderRecommendationText } from "../lib/inlineMarkdown";
import { AIActivityAge } from "./AIActivityAge";
import { GenerationStreamPreview } from "./GenerationStreamPreview";
import type { ReportBatchPreview } from "../api/types";
import { AI_ACTIVITY_LABELS } from "../lib/generationFeedback";

// Large state marks beside a batch's line; the state text next to them stays the accessible name.
function CheckIcon() {
  return <svg className="generation-batch-icon generation-batch-icon-success" viewBox="0 0 24 24" width="30" height="30" aria-hidden="true" focusable="false">
    <path d="M4 12.5 9.5 18 20 6.5" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
  </svg>;
}

function CrossIcon() {
  return <svg className="generation-batch-icon generation-batch-icon-failed" viewBox="0 0 24 24" width="30" height="30" aria-hidden="true" focusable="false">
    <path d="M6 6 18 18M18 6 6 18" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
  </svg>;
}

function BatchPreview({ batch, total, terminal, succeeded, pendingLabel }: {
  batch: ReportBatchPreview; total: number; terminal?: boolean; succeeded?: boolean; pendingLabel?: string;
}) {
  const field = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (field.current) field.current.scrollTop = field.current.scrollHeight;
  }, [batch.reportPreview]);
  const title = tr("interface.preview_batch_title", { index: batch.index, total });
  const stateLabels = {
    pending: terminal ? tr("interface.preview_batch_not_started") : tr("interface.preview_batch_waiting"),
    running: batch.aiActivity ? AI_ACTIVITY_LABELS[batch.aiActivity.phase] : pendingLabel ?? tr("interface.preview_processing"),
    validated: tr("interface.preview_batch_validated"),
    failed: tr("interface.preview_batch_failed"),
    cancelled: tr("interface.preview_batch_cancelled"),
    timed_out: tr("interface.preview_batch_timed_out"),
  };
  const hasRawOutput = !succeeded && Boolean(batch.streamPreview || batch.thinkingPreview);
  const validated = batch.state === "validated";
  // The batch's final result lives inside its section, so a folded batch shows nothing of it.
  const foldable = hasRawOutput || validated;
  // A finished batch shows its whole-batch average; a running one the live rate.
  const liveRate = batch.streamTokensPerSecond ?? batch.thinkingTokensPerSecond;
  const rate = validated ? batch.averageTokensPerSecond ?? liveRate : liveRate;
  const notStarted = batch.state === "pending" && terminal;
  const icon = validated ? <CheckIcon />
    : ["failed", "cancelled", "timed_out"].includes(batch.state) || notStarted ? <CrossIcon />
      : batch.state === "running" ? <span className="loader" aria-hidden="true" /> : null;
  // One line: the batch title, its state, its speed and the state icon; with a result or raw AI
  // output the line is the <summary> that opens the batch (folded by default), so the disclosure
  // arrow sits on the title itself.
  const heading = <span className="generation-batch-heading-row">
    <h5>{title}</h5>
    <span className="generation-batch-state"> – {stateLabels[batch.state]}</span>
    {rate != null && Number.isFinite(rate) && rate >= 0 && (
      <span className="generation-batch-state" title={tr("interface.preview_speed_hint")}>
        {tr("common.token_rate", { tokens_per_second: Math.round(rate) })}
      </span>
    )}
    {icon}
  </span>;
  return <section className="generation-stream-preview generation-batch-preview" aria-label={title}>
    {foldable ? <details>
      <summary>{heading}</summary>
      <div className="generation-live-output">
        {hasRawOutput && batch.thinkingPreview && <GenerationStreamPreview
          text={batch.thinkingPreview}
          title={tr("interface.generate_analysis_title")}
          label={`${title}: ${tr("interface.generate_analysis_label")}`}
        />}
        {hasRawOutput && batch.streamPreview && <GenerationStreamPreview
          text={batch.streamPreview}
          title={tr("interface.generate_answer_label")}
          label={`${title}: ${tr("interface.generate_answer_label")}`}
        />}
        {validated && <section className="generation-stream-preview" aria-label={tr("interface.preview_batch_result_title")}>
          <h4>{tr("interface.preview_batch_result_title")}</h4>
          <div ref={field} className="generation-report-text" tabIndex={0} aria-label={`${title}: ${tr("interface.preview_content_label")}`}>
            {batch.reportPreview ? renderRecommendationText(batch.reportPreview) : <p>{tr("interface.preview_batch_empty")}</p>}
          </div>
        </section>}
      </div>
    </details> : <div className="generation-batch-heading">{heading}</div>}
  </section>;
}

export function GenerationReportPreview({
  text, completed = 0, total = 0, terminal, succeeded, waitingInQueue,
  tokensPerSecond, activityAgeMs, activityReceivedAt,
  answer, thinking, pendingLabel,
  batches,
}: {
  text?: string | null; completed?: number; total?: number;
  terminal?: boolean; succeeded?: boolean; waitingInQueue?: boolean;
  tokensPerSecond?: number | null; activityAgeMs?: number | null; activityReceivedAt?: number;
  answer?: string | null; thinking?: string | null; pendingLabel?: string;
  batches?: ReportBatchPreview[];
}) {
  const field = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (field.current) field.current.scrollTop = field.current.scrollHeight;
  }, [text]);
  const title = terminal && !succeeded ? tr("interface.preview_incomplete_title") : tr("interface.preview_title");
  const hasRawOutput = Boolean(answer || thinking);
  // Parallel batches each measure their own speed; the total is the sum of those still running.
  const runningRates = (batches ?? [])
    .filter((batch) => batch.state === "running")
    .map((batch) => batch.streamTokensPerSecond ?? batch.thinkingTokensPerSecond)
    .filter((rate): rate is number => rate != null && Number.isFinite(rate) && rate >= 0);
  const totalRate = runningRates.length ? runningRates.reduce((sum, rate) => sum + rate, 0) : null;
  return (
    <section className="generation-stream-preview" aria-label={title}>
      <h4>
        {title}
        {total > 0 && <span>{tr("interface.preview_batch_progress", { completed, total })}</span>}
        {totalRate != null && (
          <span title={tr("interface.preview_total_speed_hint")}>
            {tr("interface.preview_total_speed", { tokens_per_second: Math.round(totalRate) })}
          </span>
        )}
        {!batches?.length && tokensPerSecond != null && Number.isFinite(tokensPerSecond) && tokensPerSecond >= 0 && (
          <span title={tr("interface.preview_speed_hint")}>
            {tr("common.token_rate", { tokens_per_second: Math.round(tokensPerSecond) })}
          </span>
        )}
      </h4>
      {batches?.length ? <div className="generation-batch-previews">
        {batches.map((batch) => <BatchPreview key={batch.index} batch={batch} total={total}
          terminal={terminal} succeeded={succeeded} pendingLabel={pendingLabel} />)}
      </div> : <>
      {(text || !hasRawOutput) && <div ref={field} className="generation-report-text" tabIndex={0} aria-label={tr("interface.preview_content_label")}>
        {text ? renderRecommendationText(text) : (
          <p>{waitingInQueue ? tr("interface.preview_queued") : terminal ? tr("interface.preview_no_valid_batches") : pendingLabel ?? tr("interface.stream_waiting")}</p>
        )}
      </div>}
      {hasRawOutput && <div className="generation-live-output">
        {thinking && <GenerationStreamPreview
          text={thinking}
          title={tr("interface.generate_analysis_title")}
          label={tr("interface.generate_analysis_label")}
        />}
        {answer && <GenerationStreamPreview
          text={answer}
          title={tr("interface.generate_answer_label")}
          label={tr("interface.generate_answer_label")}
        />}
      </div>}
      </>}
      {activityAgeMs != null && activityReceivedAt !== undefined && (
        <AIActivityAge ageMs={activityAgeMs} receivedAt={activityReceivedAt} />
      )}
    </section>
  );
}
