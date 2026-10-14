import type { HerbConditionsMessage } from "../api/types";
import { DoctorAvatar } from "./DoctorAvatar";

export function HerbConditionsPanel({ message }: { message: HerbConditionsMessage }) {
  const herbName = message.herbName.charAt(0).toLocaleUpperCase("ro-RO") + message.herbName.slice(1);
  const speciesNames = message.species.map((species) =>
    species.replace(/\p{L}+/gu, (word) => word.charAt(0).toUpperCase() + word.slice(1)),
  ).join(" · ");
  return (
    <section className="herb-conditions-panel" aria-label={`Afecțiuni asociate cu ${herbName}`}>
      <div className="chatbot-message-header">
        <DoctorAvatar />
        <h3>
          🌿 {herbName}{" "}
          <span className="herb-title-details">
            {speciesNames && <span className="herb-species">({speciesNames}) </span>}
            -- plantă utilă în <strong className="herb-condition-count">{message.entriesCount}</strong> afecțiuni
          </span>
        </h3>
      </div>
      <p className="herb-association-note">Lista reflectă asocieri din sursele locale, inclusiv atenționări și contraindicații.</p>
      {message.entriesCount === 0 ? (
        <p>Planta există în catalog, dar nu are afecțiuni asociate în indexul actual.</p>
      ) : (
        <ul className="herb-conditions-list" aria-label="Afecțiuni asociate">
          {message.conditions.map((condition) => (
            <li key={condition.id}>{condition.name}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
