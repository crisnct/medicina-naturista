import { tr } from "../lib/texts";
import type { HerbConditionsMessage, HerbEvidenceKind } from "../api/types";
import { DoctorAvatar } from "./DoctorAvatar";
import { HerbEvidencePanel } from "./HerbEvidencePanel";

export function HerbConditionsPanel({ message }: { message: HerbConditionsMessage }) {
  const herbName = message.herbName.charAt(0).toLocaleUpperCase("ro-RO") + message.herbName.slice(1);
  const speciesNames = message.species.map((species) =>
    species.replace(/\p{L}+/gu, (word) => word.charAt(0).toUpperCase() + word.slice(1)),
  ).join(" · ");
  const cautionAvailable = ["ready", "partial"].includes(message.contraindicationsStatus ?? "")
    && typeof message.contraindicationsCount === "number";
  const contraindications = message.contraindications ?? [];
  function sources(evidenceKind: HerbEvidenceKind) {
    const negative = evidenceKind === "contraindication";
    const count = negative ? message.contraindicationsCount ?? 0 : message.entriesCount;
    const available = !negative || cautionAvailable;
    if (count > 0 && available && message.groupId && message.herbId && message.positiveRunId && (!negative || message.cautionRunId)) {
      return <HerbEvidencePanel message={{ ...message, groupId: message.groupId }} evidenceKind={evidenceKind} />;
    }
    const ready = available && count === 0;
    return <details className="herb-evidence-panel">
      <summary>{ready
        ? tr("interface.herb_evidence_summary", { fragments_count: 0, documents_count: 0 })
        : tr("interface.herb_evidence_unavailable_summary")}</summary>
      <p>{tr(ready ? "interface.herb_evidence_empty" : negative ? "interface.herb_conditions_prohibition_pending" : "interface.herb_evidence_not_retained")}</p>
    </details>;
  }
  return (
    <section className="herb-conditions-panel" aria-label={tr("interface.herb_conditions_label", { herb_name: herbName })}>
      <div className="chatbot-message-header">
        <DoctorAvatar />
        <h3>
          {"🌿 "}{herbName}{" "}
          <span className="herb-title-details">
            {speciesNames && <span className="herb-species">{"("}{speciesNames}{") "}</span>}
            {tr("interface.herb_conditions_use_prefix")}<strong className="herb-condition-count">{message.entriesCount}</strong> {tr("interface.herb_conditions_count_label")}
            {cautionAvailable ? <>
              {tr("interface.herb_conditions_prohibition_prefix")}<strong className="herb-condition-count">{message.contraindicationsCount}</strong> {tr("interface.herb_conditions_prohibition_count_label")}
            </> : tr("interface.herb_conditions_prohibition_unavailable")}</span>
        </h3>
      </div>
      <section className="herb-association-section" aria-label={tr("interface.herb_conditions_positive_title")}>
        <h4>{tr("interface.herb_conditions_positive_title")}{" - "}{message.entriesCount}</h4>
        {message.entriesCount === 0 ? (
        <p>{tr("interface.herb_conditions_empty")}</p>
      ) : (
        <ul className="herb-conditions-list" aria-label={tr("interface.herb_conditions_title")}>
          {message.conditions.map((condition) => (
            <li key={condition.id}>{condition.name}</li>
          ))}
        </ul>
      )}
        {sources("positive")}
      </section>
      <section className="herb-association-section herb-contraindications-section" aria-label={tr("interface.herb_conditions_negative_title")}>
        <h4>{tr("interface.herb_conditions_negative_title")}{cautionAvailable && <> - {message.contraindicationsCount}</>}</h4>
        {!cautionAvailable ? <p>{tr("interface.herb_conditions_prohibition_pending")}</p> : <>
          {message.contraindicationsStatus === "partial" && <p className="herb-association-note">{tr("interface.herb_conditions_prohibition_partial")}</p>}
          {contraindications.length === 0 ? <p>{tr("interface.herb_conditions_prohibition_empty")}</p> : <ul className="herb-conditions-list" aria-label={tr("interface.herb_conditions_negative_title")}>
            {contraindications.map((condition) => <li key={condition.id}>
              {condition.name}
            </li>)}
          </ul>}
        </>}
        {sources("contraindication")}
      </section>
    </section>
  );
}
