import { useEffect, useRef } from "react";
import { AIActivityAge } from "./AIActivityAge";

export function GenerationStreamPreview({
  text,
  title = "Ultimul fragment primit de la AI",
  label = "Textul primit de la AI, în curs de generare",
  placeholder = "Aștept primul fragment de text…",
  activityAgeMs,
  activityReceivedAt,
}: {
  text?: string | null; title?: string; label?: string; placeholder?: string;
  activityAgeMs?: number | null; activityReceivedAt?: number;
}) {
  const field = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (field.current) field.current.scrollTop = field.current.scrollHeight;
  }, [text, title]);

  return (
    <section className="generation-stream-preview" aria-label={title}>
      <h4>{title}</h4>
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
