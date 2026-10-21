import { tr } from "../lib/texts";
import { useEffect, useRef } from "react";
import { AIActivityAge } from "./AIActivityAge";

export function GenerationStreamPreview({
  text,
  title = tr("common.ai_answer_title"),
  label = tr("interface.stream_content_label"),
  placeholder = tr("interface.stream_waiting"),
  activityAgeMs,
  activityReceivedAt,
  tokensPerSecond,
}: {
  text?: string | null; title?: string; label?: string; placeholder?: string;
  activityAgeMs?: number | null; activityReceivedAt?: number;
  tokensPerSecond?: number | null;
}) {
  const field = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (field.current) field.current.scrollTop = field.current.scrollHeight;
  }, [text, title]);

  return (
    <section className="generation-stream-preview" aria-label={title}>
      <h4>
        {title}
        {tokensPerSecond != null && Number.isFinite(tokensPerSecond) && tokensPerSecond >= 0 && (
          <span title={tr("interface.stream_speed_hint")}>
            {tr("common.token_rate", { tokens_per_second: Math.round(tokensPerSecond) })}
          </span>
        )}
      </h4>
      <textarea
        ref={field}
        className="generation-stream-text"
        aria-label={label}
        readOnly
        rows={10}
        value={text ? `${text}.....` : ""}
        placeholder={placeholder}
        spellCheck={false}
      />
      {activityAgeMs != null && activityReceivedAt !== undefined && (
        <AIActivityAge ageMs={activityAgeMs} receivedAt={activityReceivedAt} />
      )}
    </section>
  );
}
