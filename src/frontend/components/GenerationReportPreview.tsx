import { tr } from "../lib/texts";
import { useEffect, useRef } from "react";
import { renderRecommendationText } from "../lib/inlineMarkdown";
import { AIActivityAge } from "./AIActivityAge";

export function GenerationReportPreview({
  text, completed = 0, total = 0, terminal, succeeded, waitingInQueue,
  tokensPerSecond, activityAgeMs, activityReceivedAt,
}: {
  text?: string | null; completed?: number; total?: number;
  terminal?: boolean; succeeded?: boolean; waitingInQueue?: boolean;
  tokensPerSecond?: number | null; activityAgeMs?: number | null; activityReceivedAt?: number;
}) {
  const field = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (field.current) field.current.scrollTop = field.current.scrollHeight;
  }, [text]);
  const title = terminal && !succeeded ? tr("interface.preview_incomplete_title") : tr("interface.preview_title");
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
      <div ref={field} className="generation-report-text" tabIndex={0} aria-label={tr("interface.preview_content_label")}>
        {text ? renderRecommendationText(text) : (
          <p>{waitingInQueue ? tr("interface.preview_queued") : terminal ? tr("interface.preview_no_valid_batches") : tr("interface.preview_processing")}</p>
        )}
      </div>
      {activityAgeMs != null && activityReceivedAt !== undefined && (
        <AIActivityAge ageMs={activityAgeMs} receivedAt={activityReceivedAt} />
      )}
    </section>
  );
}
