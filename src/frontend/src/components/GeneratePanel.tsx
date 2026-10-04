import { useState } from "react";
import type { FragmentItem, GenerateMessage } from "../api/types";
import { countReachingMinScore, MIN_SCORE_OPTIONS } from "../lib/scoreFilter";

export function GeneratePanel({
  message,
  fragments,
  onGenerate,
}: {
  message: GenerateMessage;
  // The fragments of the same search; absent when that message is no longer
  // in the chat, in which case the server alone checks the threshold.
  fragments?: FragmentItem[];
  onGenerate: (searchId: string, minScore: number) => void;
}) {
  // Only fragments whose relevance reaches this are sent to the AI (0 = all).
  const [minScore, setMinScore] = useState(0);
  const noneReach = fragments !== undefined && countReachingMinScore(fragments, minScore) === 0;
  const disabled = message.busy || noneReach;

  return (
    <section className="generate-recipe-panel">
      <div className="generate-recipe-copy">
        Trimite-le la AI pentru a le combina și generează apoi documentul cu recomandări
        {noneReach && <span className="generate-recipe-warning">Niciun fragment nu atinge scorul minim selectat.</span>}
      </div>
      <div className="generate-recipe-actions">
        <label className="fragments-panel-filter">
          Scor minim
          <select
            value={minScore}
            disabled={message.busy}
            onChange={(event) => setMinScore(Number(event.target.value))}
          >
            {MIN_SCORE_OPTIONS.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="generate-inline"
          disabled={disabled}
          aria-disabled={disabled}
          onClick={() => onGenerate(message.searchId, minScore)}
        >
          {message.busy ? "⏳ Se generează rețeta..." : "💊 Generează rețeta"}
        </button>
      </div>
    </section>
  );
}
