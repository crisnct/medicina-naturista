import { useEffect, useRef, useState, type FormEvent } from "react";

const MAX_CHAT_CHARS = 4000;

export function Composer({
  disabled,
  processing,
  onSend,
}: {
  disabled: boolean;
  processing: boolean;
  onSend: (message: string, onAccepted: () => void) => void;
}) {
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const busy = disabled || submitting;

  useEffect(() => {
    if (!processing) setSubmitting(false);
  }, [processing]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || busy) return;
    setSubmitting(true);
    onSend(trimmed, () => setValue(""));
  };

  return (
    <>
      <div className="question-examples" aria-label="Exemple de întrebări">
        <span>Exemple de întrebări</span>
        {[
          { label: "🌿 Remedii naturiste pentru gripă", text: "Remedii naturiste pentru gripă" },
          { label: "🌿 Despre cuișoare", text: "Spune-mi tot ce știi despre Cuișoare" },
          { label: "🌿 Top 10 plante medicinale", text: "Top 10 plante medicinale" },
          { label: "📚 Despre Ovidiu Bojor", text: "Spune-mi tot ce știi despre Ovidiu Bojor" },
          { label: "🍄 Despre cultivarea ciupercilor", text: "Spune-mi tot ce știi despre cultivarea ciupercilor comestibile" },
          { label: "🧄 La ce e bun usturoiul ?", text: "La ce e bun usturoiul ?" },
        ].map((example) => (
          <button key={example.label} type="button" className="example-button"
            disabled={busy || value.trim().length > 0}
            onClick={() => { setValue(example.text); input.current?.focus({ preventScroll: true }); }}>
            {example.label}
          </button>
        ))}
      </div>
      <form id="message-row" onSubmit={submit}>
        <label htmlFor="health-message">Întrebarea dumneavoastră</label>
        <input
          ref={input}
          id="health-message"
          type="text"
          enterKeyHint="send"
          placeholder="De exemplu: Remedii naturiste pentru gripă…"
          aria-describedby="message-helper"
          maxLength={MAX_CHAT_CHARS}
          disabled={busy}
          value={value}
          onChange={(event) => setValue(event.target.value)}
        />
        <div id="message-helper">Pentru o căutare lexicală mai bună, separați prin virgulă sinonimele unei afecțiuni sau afecțiunile înrudite.</div>
        <div className="composer-actions">
          <button id="send-message" type="submit" disabled={busy || value.trim().length === 0}>
            {processing ? "⏳ În curs…" : (
              <>
                <svg className="send-question-icon" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
                  <path d="m22 2-7 20-4-9-9-4Z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M22 2 11 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                </svg>
                <span>Trimite întrebarea</span>
              </>
            )}
          </button>
        </div>
      </form>
    </>
  );
}
