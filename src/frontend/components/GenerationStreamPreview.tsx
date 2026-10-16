import { useEffect, useRef } from "react";
import { AIActivityAge } from "./AIActivityAge";

export function GenerationStreamPreview({
  text,
  title = "AI generează răspunsul",
  label = "Textul primit de la AI, în curs de generare",
  placeholder = "Aștept primul fragment de text…",
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
          <span title="Viteză medie estimată din fragmentele primite: aproximativ 4 caractere per token, fără timpul de așteptare inițial.">
            {` - ${Math.round(tokensPerSecond)} tokeni/sec`}
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
