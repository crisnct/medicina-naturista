import { useState } from "react";
import type { FragmentsMessage } from "../api/types";

export function FragmentsPanel({ message }: { message: FragmentsMessage }) {
  const [open, setOpen] = useState(false);
  return (
    <details className="fragments-panel-inner" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary className="fragments-panel-banner">
        Am găsit {message.fragmentsCount} fragmente relevante în {message.documentsCount} documente locale (le puteți
        vedea mai jos). Dacă vi se par potrivite, apăsați „Generează rețeta”.
      </summary>
      <div className="fragments-panel-list">
        {message.fragments.map((fragment, index) => {
          const scoreParts: string[] = [];
          if (fragment.relevancePercent !== null) scoreParts.push(`Scor relevanță: ${Math.round(fragment.relevancePercent)}%`);
          if (fragment.matchLabel) scoreParts.push(fragment.matchLabel);
          scoreParts.push(fragment.document);
          return (
            <div className="fragments-panel-fragment" key={index}>
              <p className="fragments-panel-fragment-text">{fragment.text}</p>
              <p className="fragments-panel-fragment-score">{scoreParts.join(", ")}</p>
            </div>
          );
        })}
        <p className="fragments-panel-summary">
          Total: {message.fragmentsCount} fragmente din {message.documentsCount} documente.
        </p>
      </div>
    </details>
  );
}
