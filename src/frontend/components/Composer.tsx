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
        <span aria-hidden="true">📝</span> Specificați strict problema de sănătate și nimic altceva. Puteți menționa
        mai multe sinonime separate prin virgulă.
      </div>
      <form id="message-row" onSubmit={submit}>
        <input
          id="health-message"
          type="text"
          placeholder="Problema de sănătate..."
          aria-label="Descrieți problema de sănătate"
          aria-describedby="message-helper"
          maxLength={MAX_CHAT_CHARS}
          value={value}
          onChange={(event) => setValue(event.target.value)}
        />
        <button id="send-message" type="submit" disabled={disabled || value.trim().length === 0}>
          {processing ? "⏳ Caută..." : "📨 Trimite"}
        </button>
      </form>
    </>
  );
}
