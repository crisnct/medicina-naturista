import { tr } from "../lib/texts";
import { useEffect, useRef } from "react";
import { renderRecommendationText } from "../lib/inlineMarkdown";
import { AIActivityAge } from "./AIActivityAge";
import { GenerationStreamPreview } from "./GenerationStreamPreview";
import type { ReportBatchPreview } from "../api/types";
import { AI_ACTIVITY_LABELS } from "../lib/generationFeedback";

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
  return <section className="generation-stream-preview generation-batch-preview" aria-label={title}>
    <h5>{title}</h5>
    <p className="generation-batch-state">{stateLabels[batch.state]}</p>
    {batch.state === "validated" && <div ref={field} className="generation-report-text" tabIndex={0} aria-label={`${title}: ${tr("interface.preview_content_label")}`}>
      {batch.reportPreview ? renderRecommendationText(batch.reportPreview) : <p>{tr("interface.preview_batch_empty")}</p>}
    </div>}
    {hasRawOutput && <details open={batch.state !== "validated"}>
      <summary>{tr("interface.preview_batch_details")}</summary>
      <div className="generation-live-output">
        {batch.thinkingPreview && <GenerationStreamPreview
          text={batch.thinkingPreview}
          title={tr("interface.generate_analysis_title")}
          label={`${title}: ${tr("interface.generate_analysis_label")}`}
        />}
        {batch.streamPreview && <GenerationStreamPreview
          text={batch.streamPreview}
          title={tr("interface.generate_answer_label")}
          label={`${title}: ${tr("interface.generate_answer_label")}`}
        />}
      </div>
    </details>}
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
  return (
    <section className="generation-stream-preview" aria-label={title}>
      <h4>
        {title}
        {total > 0 && <span>{tr("interface.preview_batch_progress", { completed, total })}</span>}
        {tokensPerSecond != null && Number.isFinite(tokensPerSecond) && tokensPerSecond >= 0 && (
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
