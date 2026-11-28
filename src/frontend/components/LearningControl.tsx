import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ApiError } from "../api/client";
import type { LearningLanguageState, LearningLevelState, LearningOutdatedReason, LearningState } from "../api/types";
import { useLearning, useStartLearning, useStopLearning } from "../hooks/useLearning";
import { locale, tr } from "../lib/texts";

const STATUS_LABELS = {
  not_implemented: "interface.learning_status_not_implemented",
  running: "interface.learning_status_running",
  stopping: "interface.learning_status_stopping",
  paused_for_report: "interface.learning_status_paused_for_report",
  queued: "interface.learning_status_queued",
  published: "interface.learning_status_published",
  partial: "interface.learning_status_partial",
  stopped: "interface.learning_status_stopped",
  failed: "interface.learning_status_failed",
  not_built: "interface.learning_status_not_built",
} as const;
const OUTDATED_LABELS = {
  model: "interface.learning_outdated_model",
  prompt: "interface.learning_outdated_prompt",
  index: "interface.learning_outdated_index",
  lower_level: "interface.learning_outdated_lower_level",
} as const;
const LEVEL_NAMES = {
  1: "interface.learning_level_1",
  2: "interface.learning_level_2",
  3: "interface.learning_level_3",
  4: "interface.learning_level_4",
} as const;
const PHASE_LABELS = {
  extracting: "interface.learning_phase_extracting",
  embedding: "interface.learning_phase_embedding",
} as const;
// A level whose build process exists: it can be stopped, not started.
const WORKING = new Set(["running", "stopping", "paused_for_report"]);
// Unfinished runs of a language, whose saved progress the next start continues.
const UNFINISHED_RUNS = new Set(["queued", "running", "paused", "stopping", "failed"]);

const number = (value: number) => value.toLocaleString(locale());

function formatEta(seconds: number): string {
  if (seconds < 60) return tr("interface.learning_eta_less_than_minute");
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return tr("interface.learning_eta_minutes", { minutes });
  return tr("interface.learning_eta_hours", { hours: Math.floor(minutes / 60), minutes: minutes % 60 });
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleString(locale(), { dateStyle: "short", timeStyle: "short" });
}

function outdatedText(reasons: LearningOutdatedReason[]): string {
  return tr("interface.learning_outdated", { reasons: reasons.map((reason) => tr(OUTDATED_LABELS[reason])).join(", ") });
}

// The button's short state: the level at work and its time left, else "stopped".
function summary(state: LearningState | undefined, failed: boolean): string | null {
  if (failed) return tr("interface.learning_summary_unavailable");
  if (state === undefined) return null;
  const working = state.levels.find((level) => WORKING.has(level.status));
  if (working) {
    const level = working.level;
    if (working.status === "stopping") return tr("interface.learning_summary_stopping", { level });
    if (working.status === "paused_for_report") return tr("interface.learning_summary_paused", { level });
    return working.etaSeconds === null
      ? tr("interface.learning_summary_estimating", { level })
      : tr("interface.learning_summary_running", { level, eta: formatEta(working.etaSeconds) });
  }
  const queued = state.levels.find((level) => level.status === "queued");
  if (queued) return tr("interface.learning_summary_queued", { level: queued.level });
  return tr("interface.learning_summary_stopped");
}

function commandError(error: unknown): string {
  return error instanceof ApiError && error.code ? error.message : tr("interface.learning_command_failed");
}

function stateError(error: unknown): string {
  return error instanceof ApiError && error.code ? error.message : tr("interface.learning_state_failed");
}

function LanguageLine({ item }: { item: LearningLanguageState }) {
  const language = item.language.toUpperCase();
  const parts = [
    item.published
      ? tr("interface.learning_language_published", { language, date: formatDate(item.published) })
      : tr("interface.learning_language_not_published", { language }),
  ];
  if (item.runStatus && UNFINISHED_RUNS.has(item.runStatus) && item.unitsTotal !== null && item.unitsDone !== null) {
    parts.push(tr("interface.learning_units", { done: number(item.unitsDone), total: number(item.unitsTotal) }));
  }
  if (item.outdated.length > 0) parts.push(outdatedText(item.outdated));
  return <li>{parts.join(" · ")}</li>;
}

function LevelRow({ level, state, busy, onStart, onStop }: {
  level: LearningLevelState;
  state: LearningState;
  busy: boolean;
  onStart: (level: number) => void;
  onStop: (level: number) => void;
}) {
  const working = WORKING.has(level.status);
  const progress = level.unitsDone !== null && level.unitsTotal !== null && level.unitsTotal > 0
    ? Math.min(100, Math.round((level.unitsDone / level.unitsTotal) * 100))
    : null;
  const phase = level.phase && level.phase in PHASE_LABELS ? tr(PHASE_LABELS[level.phase as keyof typeof PHASE_LABELS]) : null;
  const eta = level.status !== "running" ? null
    : level.etaSeconds === null ? tr("interface.learning_eta_estimating") : formatEta(level.etaSeconds);
  const canCommand = state.agentAvailable && !busy;
  let command;
  if (!level.implemented) {
    command = <button type="button" className="learning-command" disabled>{tr("interface.learning_start")}</button>;
  } else if (working) {
    command = (
      <button type="button" className="learning-command learning-command-stop"
        disabled={!canCommand || level.status === "stopping"} onClick={() => onStop(level.level)}>
        {tr("interface.learning_stop")}
      </button>
    );
  } else if (level.status === "queued") {
    command = (
      <button type="button" className="learning-command" disabled={!canCommand} onClick={() => onStop(level.level)}>
        {tr("interface.learning_cancel")}
      </button>
    );
  } else {
    command = (
      <button type="button" className="learning-command learning-command-start"
        disabled={!canCommand || state.indexMaintenance || state.externalBuild} onClick={() => onStart(level.level)}>
        {tr("interface.learning_start")}
      </button>
    );
  }
  return (
    <tr className={level.implemented ? undefined : "learning-row-disabled"}>
      <th scope="row">
        <span className="learning-level">L{level.level}</span>
        <span className="learning-level-name">{tr(LEVEL_NAMES[level.level as keyof typeof LEVEL_NAMES])}</span>
      </th>
      <td>
        <span className={`learning-status learning-status-${level.status}`}>{tr(STATUS_LABELS[level.status])}</span>
        {level.outdated.length > 0 && level.status === "published" && (
          <span className="learning-outdated">{outdatedText(level.outdated)}</span>
        )}
        {level.implemented && (
          <ul className="learning-languages">
            {level.languages.map((item) => <LanguageLine key={item.language} item={item} />)}
          </ul>
        )}
      </td>
      <td>
        {progress !== null && level.unitsDone !== null && level.unitsTotal !== null ? (
          <>
            <span>{tr("interface.learning_units", { done: number(level.unitsDone), total: number(level.unitsTotal) })}</span>
            <span className="learning-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
              <span style={{ width: `${progress}%` }} />
            </span>
            {phase && <span className="learning-phase">{phase}</span>}
          </>
        ) : "—"}
      </td>
      <td className="learning-eta">{eta ?? "—"}</td>
      <td className="learning-model">{level.model}</td>
      <td>{command}</td>
    </tr>
  );
}

function LearningDialog({ state, error, onClose }: {
  state: LearningState | undefined;
  error: unknown;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const start = useStartLearning();
  const stop = useStopLearning();
  const [stopRequested, setStopRequested] = useState(false);
  // A start whose lower level is unpublished asks first; the server's message holds the question.
  const [confirmLower, setConfirmLower] = useState<{ level: number; message: string } | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const previousFocus = document.activeElement;
    if (typeof dialog.showModal === "function") dialog.showModal();
    return () => {
      if (typeof dialog.close === "function") dialog.close();
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus({ preventScroll: true });
    };
  }, []);

  const busy = start.isPending || stop.isPending;
  const startLevel = (level: number | null, includeLower = false) => {
    setConfirmLower(null);
    stop.reset();
    start.mutate({ level, includeLower }, {
      onSuccess: () => setStopRequested(false),
      onError: (failure) => {
        if (level !== null && failure instanceof ApiError && failure.code === "KNOWLEDGE_LOWER_LEVEL_REQUIRED") {
          start.reset();
          setConfirmLower({ level, message: failure.message });
        }
      },
    });
  };
  const stopLevel = (level: number | null) => {
    setConfirmLower(null);
    start.reset();
    stop.mutate(level, { onSuccess: () => setStopRequested(true) });
  };

  const levels = state?.levels ?? [];
  const working = levels.some((level) => WORKING.has(level.status) || level.status === "queued");
  const failedExit = state?.lastExit?.outcome === "failed" ? state.lastExit : null;
  const commandFailure = start.error ?? stop.error;

  return createPortal(
    <dialog ref={dialogRef} className="learning-dialog" aria-labelledby="learning-dialog-title"
      onCancel={(event) => { event.preventDefault(); onClose(); }}>
      <header className="learning-dialog-header">
        <h2 id="learning-dialog-title">{tr("interface.learning_title")}</h2>
        <button type="button" className="learning-dialog-close" aria-label={tr("interface.learning_close")}
          title={tr("interface.learning_close")} onClick={onClose}>×</button>
      </header>
      <p className="learning-note">{tr("interface.learning_start_note")}</p>
      {state === undefined ? (
        error ? <p className="learning-alert" role="alert">{stateError(error)}</p>
          : <span className="loader" aria-hidden="true" />
      ) : (
        <>
          {!state.agentAvailable && <p className="learning-alert" role="status">{tr("interface.learning_agent_unavailable")}</p>}
          {state.indexMaintenance && <p className="learning-alert" role="status">{tr("interface.learning_index_maintenance")}</p>}
          {state.externalBuild && <p className="learning-alert" role="status">{tr("interface.learning_external_build")}</p>}
          {state.pausedForReport && <p className="learning-info" role="status">{tr("interface.learning_paused_for_report")}</p>}
          {failedExit && !working && (
            <p className="learning-alert" role="status">
              {tr("interface.learning_last_failed", {
                level: failedExit.level ?? "?",
                error: failedExit.error ?? tr("interface.learning_last_failed_unknown"),
              })}
            </p>
          )}
          <div className="learning-table-wrap">
            <table className="learning-table">
              <thead>
                <tr>
                  <th scope="col">{tr("interface.learning_column_level")}</th>
                  <th scope="col">{tr("interface.learning_column_status")}</th>
                  <th scope="col">{tr("interface.learning_column_progress")}</th>
                  <th scope="col" title={tr("interface.learning_eta_note")}>{tr("interface.learning_column_eta")}</th>
                  <th scope="col" className="learning-model">{tr("interface.learning_column_model")}</th>
                  <th scope="col">{tr("interface.learning_column_command")}</th>
                </tr>
              </thead>
              <tbody>
                {levels.map((level) => (
                  <LevelRow key={level.level} level={level} state={state} busy={busy}
                    onStart={(value) => startLevel(value)} onStop={stopLevel} />
                ))}
              </tbody>
            </table>
          </div>
          <p className="learning-footnote">{tr("interface.learning_eta_note")}</p>
          {(stopRequested || levels.some((level) => level.status === "stopping")) && (
            <p className="learning-info" role="status">{tr("interface.learning_stop_note")}</p>
          )}
          {confirmLower && (
            <div className="learning-confirm" role="alertdialog" aria-label={confirmLower.message}>
              <p>{confirmLower.message}</p>
              <div className="learning-actions">
                <button type="button" className="first-visit-confirm learning-primary" disabled={busy}
                  onClick={() => startLevel(confirmLower.level, true)}>{tr("interface.learning_confirm_yes")}</button>
                <button type="button" className="secondary-button" onClick={() => setConfirmLower(null)}>
                  {tr("interface.learning_confirm_no")}
                </button>
              </div>
            </div>
          )}
          {commandFailure && <p className="learning-alert" role="alert">{commandError(commandFailure)}</p>}
          <div className="learning-actions">
            <button type="button" className="first-visit-confirm learning-primary"
              disabled={busy || working || !state.agentAvailable || state.indexMaintenance || state.externalBuild}
              onClick={() => startLevel(null)}>
              {tr("interface.learning_start_all")}
            </button>
            <button type="button" className="secondary-button"
              disabled={busy || !state.agentAvailable || !(working || state.externalBuild)}
              onClick={() => stopLevel(null)}>
              {tr("interface.learning_stop_all")}
            </button>
          </div>
        </>
      )}
    </dialog>,
    document.body,
  );
}

// The admin's multilevel learning button, above the window of local models; it opens the levels.
export function LearningControl() {
  const [open, setOpen] = useState(false);
  const query = useLearning(open);
  const text = summary(query.data, query.isError && query.data === undefined);
  return (
    <>
      <button type="button" className="learning-button" aria-haspopup="dialog" aria-expanded={open}
        title={tr("interface.learning_open")} onClick={() => setOpen(true)}>
        <span aria-hidden="true">🎓</span>
        <span className="learning-button-text">
          <span className="learning-button-title">{tr("interface.learning_title")}</span>
          {text && <span className="learning-button-state">{text}</span>}
        </span>
      </button>
      {open && <LearningDialog state={query.data} error={query.error} onClose={() => setOpen(false)} />}
    </>
  );
}
