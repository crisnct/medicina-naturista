import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { locale, tr } from "../lib/texts";
import type { ModelStage } from "../lib/generationFeedback";
import type { ResourceCheck, ResourceDecision } from "../api/types";

const gigabytes = (value: number | null | undefined) =>
  typeof value === "number"
    ? value.toLocaleString(locale(), { maximumFractionDigits: 1 })
    : tr("interface.colibri_resources_unknown");

// The figures of a Colibri memory test; the planner's details stay folded, they are for the curious.
function ResourceCheckView({ check, onDecide, onCancel, pending }: {
  check: ResourceCheck;
  onDecide?: (decision: ResourceDecision) => void;
  onCancel?: () => void;
  pending?: boolean;
}) {
  const blocking = check.level === "blocking";
  const ram = typeof check.ramMinimumGb === "number" && blocking
    ? tr("interface.colibri_resources_ram_minimum", {
      available: gigabytes(check.ramAvailableGb), minimum: gigabytes(check.ramMinimumGb), recommended: gigabytes(check.ramRecommendedGb),
    })
    : tr("interface.colibri_resources_ram", { available: gigabytes(check.ramAvailableGb), recommended: gigabytes(check.ramRecommendedGb) });
  const details = [
    typeof check.expertsPerLayer === "number" ? tr("interface.colibri_resources_experts", { count: check.expertsPerLayer }) : null,
    typeof check.expertResidencyPct === "number" ? tr("interface.colibri_resources_residency", { percent: check.expertResidencyPct }) : null,
    ...check.planWarnings,
  ].filter((line): line is string => Boolean(line));
  return (
    <>
      <h2 id="model-warmup-title">{tr(blocking ? "interface.colibri_resources_blocking_title" : "interface.colibri_resources_warning_title")}</h2>
      <p id="model-warmup-body">{tr(blocking ? "interface.colibri_resources_blocking_body" : "interface.colibri_resources_warning_body")}</p>
      <ul className="resource-check-figures">
        <li>{ram}</li>
        <li>{tr("interface.colibri_resources_vram", { available: gigabytes(check.vramFreeGb), recommended: gigabytes(check.vramRecommendedGb) })}</li>
      </ul>
      {details.length > 0 && (
        <details className="resource-check-details">
          <summary>{tr("interface.colibri_resources_details")}</summary>
          <ul>{details.map((line) => <li key={line}>{line}</li>)}</ul>
        </details>
      )}
      <div className="resource-check-actions">
        {onDecide && (
          <button type="button" className="first-visit-confirm" autoFocus disabled={pending}
            onClick={() => onDecide(blocking ? "retry" : "continue")}>
            {tr(blocking ? "interface.colibri_resources_retry" : "interface.colibri_resources_continue")}
          </button>
        )}
        {onCancel && (
          <button type="button" className="secondary-button" disabled={pending} onClick={onCancel}>
            {tr("interface.colibri_resources_cancel")}
          </button>
        )}
      </div>
    </>
  );
}

// Driven by the polled job, so it reappears after a refresh and closes by itself at the next stage.
export function ModelWarmupDialog({ stage, model, onCancel, resourceCheck, onDecide, decisionPending }: {
  stage: ModelStage;
  model: string;
  onCancel?: () => void;
  resourceCheck?: ResourceCheck | null;
  onDecide?: (decision: ResourceDecision) => void;
  decisionPending?: boolean;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const unmounting = useRef(false);
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const previousFocus = document.activeElement;
    unmounting.current = false;
    dialog.showModal();
    return () => {
      unmounting.current = true;
      dialog.close();
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) {
        previousFocus.focus({ preventScroll: true });
      }
    };
  }, []);
  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const stopping = stage === "stopping_model";
  const checking = stage === "checking_resources" || (stage === "awaiting_resources" && !resourceCheck);
  const awaiting = stage === "awaiting_resources" && resourceCheck;

  return createPortal(
    <dialog
      ref={dialogRef}
      className="model-warmup-dialog"
      aria-labelledby="model-warmup-title"
      aria-describedby="model-warmup-body"
      // Esc must not hide a wait that nothing else explains; Cancel ends it deliberately.
      onCancel={(event) => event.preventDefault()}
      // Browsers close a modal dialog on a repeated Esc even when `cancel` is prevented, so a close
      // while the stage is still active opens it again; only the unmount below may close it.
      onClose={(event) => {
        const dialog = event.currentTarget;
        if (!unmounting.current && dialog.isConnected && !dialog.open) dialog.showModal();
      }}
    >
      {awaiting ? (
        <ResourceCheckView check={resourceCheck} onDecide={onDecide} onCancel={onCancel} pending={decisionPending} />
      ) : (
        <>
          <div className="model-warmup-spinner" aria-hidden="true" />
          <h2 id="model-warmup-title">
            {tr(stopping ? "interface.model_warmup_stopping_title" : checking ? "interface.model_warmup_checking_title" : "interface.model_warmup_warming_title")}
          </h2>
          <p id="model-warmup-body">
            {stopping
              ? tr("interface.model_warmup_stopping_body")
              : checking
                ? tr("interface.model_warmup_checking_body", { model })
                : tr("interface.model_warmup_warming_body", { model })}
          </p>
          {!stopping && !checking && <p className="model-warmup-note">{tr("interface.model_warmup_note")}</p>}
          <p className="model-warmup-elapsed" role="status">{tr("interface.model_warmup_elapsed", { seconds })}</p>
          {onCancel && (
            <button type="button" className="secondary-button" autoFocus onClick={onCancel}>{tr("interface.generate_cancel")}</button>
          )}
        </>
      )}
    </dialog>,
    document.body,
  );
}
