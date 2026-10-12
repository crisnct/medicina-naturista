import { useState, type FormEvent } from "react";

const MAX_CHAT_CHARS = 4000;

export function Composer({
  disabled,
  processing,
  onSend,
}: {
  disabled: boolean;
  processing: boolean;
  onSend: (message: string) => void;
}) {
  const [value, setValue] = useState("");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  };

  return (
    <>
      <div id="message-helper">
        <span aria-hidden="true">📝</span> Cereți remedii, informații despre o plantă, puneți o întrebare
        sau solicitați trimiterea raportului precedent pe email.
      </div>
      <form id="message-row" onSubmit={submit}>
        <input
          id="health-message"
          type="text"
          placeholder="Problema de sănătate, planta sau întrebarea..."
          aria-label="Scrieți mesajul"
          aria-describedby="message-helper"
          maxLength={MAX_CHAT_CHARS}
          disabled={disabled}
          value={value}
          onChange={(event) => setValue(event.target.value)}
        />
        <button id="send-message" type="submit" disabled={disabled || value.trim().length === 0}>
          {processing ? "⏳ Procesez..." : "📨 Trimite"}
        </button>
      </form>
    </>
  );
}
