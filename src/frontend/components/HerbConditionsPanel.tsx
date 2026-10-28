import { useEffect, useRef, useState } from "react";
import { herbImageUrl } from "../api/client";
import { tr } from "../lib/texts";
import type { HerbConditionsMessage, HerbEvidenceKind } from "../api/types";
import { DoctorAvatar } from "./DoctorAvatar";
import { HerbEvidencePanel } from "./HerbEvidencePanel";
import { HerbImageViewer } from "./HerbImageViewer";
import { HerbWarningsPanel } from "./HerbWarningsPanel";

// Remount for each product so an earlier image's load/error cannot alter its successor.
function HerbPositiveContent({ message, herbName }: { message: HerbConditionsMessage; herbName: string }) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const [flowsAroundImage, setFlowsAroundImage] = useState(false);
  const [imageExpanded, setImageExpanded] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const content = contentRef.current;
    const image = content?.querySelector(".herb-product-image-trigger");
    const list = content?.querySelector("ul");
    if (!loaded || !content || !image || !list) return;
    // Use the same column widths in both layouts, so wrapping cannot oscillate the choice.
    function updateFlow() {
      if (!image || !list) return;
      const imageHeight = image.getBoundingClientRect().height;
      const imageGap = parseFloat(getComputedStyle(image).marginBottom) || 0;
      const items = [...list.children];
      const textHeight = items.reduce((height, item) => {
        const style = getComputedStyle(item);
        const margin = Math.max(parseFloat(style.marginTop) || 0, parseFloat(style.marginBottom) || 0);
        return height + item.getBoundingClientRect().height + margin;
      }, 0);
      setFlowsAroundImage(items.length > 2 && textHeight > 2 * (imageHeight + imageGap));
    }
    updateFlow();
    const observer = new ResizeObserver(updateFlow);
    observer.observe(content);
    observer.observe(image);
    observer.observe(list);
    return () => observer.disconnect();
  }, [loaded, message.conditions]);
  return <><div ref={contentRef} className={`herb-positive-content${loaded ? " has-image" : ""}${loaded && flowsAroundImage ? " flows-around-image" : ""}`}>
    {message.herbId && !failed ? <button
      type="button"
      className="herb-product-image-trigger"
      hidden={!loaded}
      aria-label={tr("interface.herb_image_open", { herb_name: herbName })}
      aria-haspopup="dialog"
      onClick={() => setImageExpanded(true)}
    ><img
      className="herb-product-image"
      src={herbImageUrl(message.herbId)}
      alt={herbName}
      width={280}
      height={280}
      onLoad={(event) => setLoaded(event.currentTarget.naturalWidth > 0)}
      onError={() => { setLoaded(false); setFailed(true); }}
    /></button> : null}
    {message.entriesCount === 0 ? <p>{tr("interface.herb_conditions_empty")}</p> : (
      <ul className="herb-conditions-list" aria-label={tr("interface.herb_conditions_title")}>
        {message.conditions.map((condition) => <li key={condition.id}>{condition.name}</li>)}
      </ul>
    )}
  </div>
    {imageExpanded && loaded && message.herbId && <HerbImageViewer
      src={herbImageUrl(message.herbId)} herbName={herbName} onClose={() => setImageExpanded(false)}
    />}
  </>;
}

export function HerbConditionsPanel({ message }: { message: HerbConditionsMessage }) {
  const agreement = message.herbAgreement ?? "feminine";
  const wording = {
    masculine: {
      positive: "interface.herb_conditions_positive_title_masculine",
      negative: "interface.herb_conditions_negative_title_masculine",
    },
    feminine: {
      positive: "interface.herb_conditions_positive_title",
      negative: "interface.herb_conditions_negative_title",
    },
    plural: {
      positive: "interface.herb_conditions_positive_title_plural",
      negative: "interface.herb_conditions_negative_title_plural",
    },
  } as const;
  const labels = wording[agreement];
  const positiveTitle = tr(labels.positive);
  const negativeTitle = tr(labels.negative);
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
          </span>
        </h3>
      </div>
      <section className="herb-association-section" aria-label={positiveTitle}>
        <h4>{positiveTitle}{" - "}{message.entriesCount}</h4>
        <HerbPositiveContent key={message.herbId ?? message.herbName} message={message} herbName={herbName} />
        {sources("positive")}
      </section>
      <section className="herb-association-section herb-contraindications-section" aria-label={negativeTitle}>
        <h4>{negativeTitle}{cautionAvailable && <> - {message.contraindicationsCount}</>}</h4>
        {!cautionAvailable ? <p>{tr("interface.herb_conditions_prohibition_pending")}</p> : <>
          {message.contraindicationsStatus === "partial" && <p className="herb-association-note">{tr("interface.herb_conditions_prohibition_partial")}</p>}
          {contraindications.length === 0 ? <p>{tr("interface.herb_conditions_prohibition_empty")}</p> : <ul className="herb-conditions-list" aria-label={negativeTitle}>
            {contraindications.map((condition) => <li key={condition.id}>
              {condition.name}
            </li>)}
          </ul>}
        </>}
        {sources("contraindication")}
      </section>
      <HerbWarningsPanel message={message} />
    </section>
  );
}
