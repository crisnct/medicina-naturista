import { tr } from "../lib/texts";
import type { HerbConditionsMessage } from "../api/types";
import { DoctorAvatar } from "./DoctorAvatar";

export function HerbConditionsPanel({ message }: { message: HerbConditionsMessage }) {
  const herbName = message.herbName.charAt(0).toLocaleUpperCase("ro-RO") + message.herbName.slice(1);
  const speciesNames = message.species.map((species) =>
    species.replace(/\p{L}+/gu, (word) => word.charAt(0).toUpperCase() + word.slice(1)),
  ).join(" · ");
  return (
    <section className="herb-conditions-panel" aria-label={tr("interface.herb_conditions_label", { herb_name: herbName })}>
      <div className="chatbot-message-header">
        <DoctorAvatar />
        <h3>
          {"🌿 "}{herbName}{" "}
          <span className="herb-title-details">
            {speciesNames && <span className="herb-species">{"("}{speciesNames}{") "}</span>}
            {tr("interface.herb_conditions_use_prefix")}<strong className="herb-condition-count">{message.entriesCount}</strong> {tr("interface.herb_conditions_count_label")}</span>
        </h3>
      </div>
      {message.entriesCount === 0 ? (
        <p>{tr("interface.herb_conditions_empty")}</p>
      ) : (
        <ul className="herb-conditions-list" aria-label={tr("interface.herb_conditions_title")}>
          {message.conditions.map((condition) => (
            <li key={condition.id}>{condition.name}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
