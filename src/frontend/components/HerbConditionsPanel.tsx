import type { HerbConditionsMessage } from "../api/types";

export function HerbConditionsPanel({ message }: { message: HerbConditionsMessage }) {
  return (
    <section className="herb-conditions-panel" aria-label={`Afecțiuni asociate cu ${message.herbName}`}>
      <h3>🌿 {message.herbName} — utilă în {message.entriesCount} afecțiuni</h3>
      <p className="herb-species">{message.species.join(" · ")}</p>
      {message.entriesCount === 0 ? (
        <p>Planta există în catalog, dar nu are afecțiuni asociate în indexul actual.</p>
      ) : (
        <div className="herb-conditions-table">
          <table>
            <thead><tr><th scope="col">Afecțiune</th></tr></thead>
            <tbody>{message.conditions.map((condition) => (
              <tr key={condition.id}><td>{condition.name}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
      <p className="herb-association-note">Lista reflectă asocieri din sursele locale, inclusiv atenționări și contraindicații.</p>
    </section>
  );
}
