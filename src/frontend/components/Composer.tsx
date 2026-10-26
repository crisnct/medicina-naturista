import { tr } from "../lib/texts";
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
      <form id="message-row" onSubmit={submit}>
        <label htmlFor="health-message">{tr("interface.composer_question_label")}</label>
        <div className="composer-input-row">
          <input
            ref={input}
            id="health-message"
            type="text"
            enterKeyHint="send"
            placeholder={tr("interface.composer_placeholder")}
            aria-describedby="message-helper"
            maxLength={MAX_CHAT_CHARS}
            disabled={busy}
            value={value}
            onChange={(event) => setValue(event.target.value)}
          />
          <button id="send-message" type="submit" disabled={busy || value.trim().length === 0}>
            {processing ? tr("interface.composer_processing") : (
              <>
                <svg className="send-question-icon" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
                  <path d="m22 2-7 20-4-9-9-4Z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M22 2 11 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                </svg>
                <span>{tr("interface.composer_send")}</span>
              </>
            )}
          </button>
        </div>
        <div id="message-helper">{tr("interface.composer_search_hint")}</div>
        <div className="question-examples" aria-label={tr("interface.composer_examples_label")}>
          {[
            { label: tr("interface.example_flu_label"), text: tr("interface.example_flu_query") },
            { label: tr("interface.example_cloves_label"), text: tr("interface.example_cloves_query") },
            { label: tr("interface.example_top_products_label"), text: tr("interface.example_top_products_query") },
            { label: tr("interface.example_top_flu_label"), text: tr("interface.example_top_flu_query") },
            { label: tr("interface.example_author_label"), text: tr("interface.example_author_query") },
            { label: tr("interface.example_mushrooms_label"), text: tr("interface.example_mushrooms_query") },
            { label: tr("interface.example_garlic_label"), text: tr("interface.example_garlic_query") },
          ].map((example) => (
            <button key={example.label} type="button" className="example-button"
              disabled={busy || value.trim().length > 0}
              onClick={() => { setValue(example.text); input.current?.focus({ preventScroll: true }); }}>
              {example.label}
            </button>
          ))}
        </div>
      </form>
    </>
  );
}
