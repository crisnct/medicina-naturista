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
  const title = terminal && !succeeded ? "Previzualizare incompletă" : "Previzualizare raport";
  return (
    <section className="generation-stream-preview" aria-label={title}>
      <h4>
        {title}
        {total > 0 && <span>{` — ${completed}/${total} loturi finalizate`}</span>}
        {tokensPerSecond != null && Number.isFinite(tokensPerSecond) && tokensPerSecond >= 0 && (
          <span title="Viteză aproximativă, estimată la 4 caractere per token.">
            {` - ${Math.round(tokensPerSecond)} tokeni/sec`}
          </span>
        )}
      </h4>
      <div ref={field} className="generation-report-text" tabIndex={0} aria-label="Conținutul previzualizării raportului">
        {text ? renderRecommendationText(text) : (
          <p>{waitingInQueue ? "Raportul așteaptă în coadă." : terminal ? "Niciun lot validat disponibil." : "Se procesează loturile…"}</p>
        )}
      </div>
      {activityAgeMs != null && activityReceivedAt !== undefined && (
        <AIActivityAge ageMs={activityAgeMs} receivedAt={activityReceivedAt} />
      )}
    </section>
  );
}
