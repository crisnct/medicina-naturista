import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { tr } from "../lib/texts";
import type { ModelStage } from "../lib/generationFeedback";

// Driven by the polled job, so it reappears after a refresh and closes by itself at the next stage.
export function ModelWarmupDialog({ stage, model, onCancel }: {
  stage: ModelStage;
  model: string;
  onCancel?: () => void;
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
      <div className="model-warmup-spinner" aria-hidden="true" />
      <h2 id="model-warmup-title">{tr(stopping ? "interface.model_warmup_stopping_title" : "interface.model_warmup_warming_title")}</h2>
      <p id="model-warmup-body">{stopping ? tr("interface.model_warmup_stopping_body") : tr("interface.model_warmup_warming_body", { model })}</p>
      {!stopping && <p className="model-warmup-note">{tr("interface.model_warmup_note")}</p>}
      <p className="model-warmup-elapsed" role="status">{tr("interface.model_warmup_elapsed", { seconds })}</p>
      {onCancel && (
        <button type="button" className="secondary-button" autoFocus onClick={onCancel}>{tr("interface.generate_cancel")}</button>
      )}
    </dialog>,
    document.body,
  );
}
