import type { GenerateMessage } from "../api/types";

export function GeneratePanel({
  message,
  onGenerate,
}: {
  message: GenerateMessage;
  onGenerate: (searchId: string) => void;
}) {
  return (
    <section className="generate-recipe-panel">
      <div className="generate-recipe-copy">
        <strong>
          Trimite-le la AI pentru a le combina și generează apoi documentul cu recomandări
        </strong>
      </div>
      <button
        type="button"
        className="generate-inline"
        disabled={message.busy}
        aria-disabled={message.busy}
        onClick={() => onGenerate(message.searchId)}
      >
        {message.busy ? "⏳ Se generează rețeta..." : "💊 Generează rețeta"}
      </button>
    </section>
  );
}
