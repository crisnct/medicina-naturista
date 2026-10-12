import type { HerbConditionsMessage } from "../api/types";

export function HerbConditionsPanel({ message }: { message: HerbConditionsMessage }) {
  return (
    <section className="herb-conditions-panel" aria-label={`Afecțiuni asociate cu ${message.herbName}`}>
      <h3>🌿 {message.herbName} — utilă în {message.entriesCount} afecțiuni</h3>
      <p className="herb-species">{message.species.join(" · ")}</p>
      {message.entriesCount === 0 ? (
        <p>Planta există în catalog, dar nu are afecțiuni asociate în indexul actual.</p>
      ) : (
        <ul className="herb-conditions-list" aria-label="Afecțiuni asociate">
          {message.conditions.map((condition) => (
            <li key={condition.id}>{condition.name}</li>
          ))}
        </ul>
      )}
      <p className="herb-association-note">Lista reflectă asocieri din sursele locale, inclusiv atenționări și contraindicații.</p>
    </section>
  );
}
