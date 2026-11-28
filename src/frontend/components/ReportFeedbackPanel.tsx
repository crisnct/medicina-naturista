import { useId, useState } from "react";
import { api, errorMessage } from "../api/client";
import { tr } from "../lib/texts";

const SCORES = Array.from({ length: 11 }, (_, score) => score);
// A report rated at least this high may be kept as an example (the server applies the same rule).
const EXAMPLE_MIN_SCORE = 8;
const MAX_COMMENT_CHARS = 4000;

type Status = { kind: "idle" } | { kind: "saving" } | { kind: "saved" } | { kind: "failed"; message: string };

// The admin's rating of one published report, given once: the panel disappears when it is saved
// (the server also marks the message, so it stays hidden after a reload).
export function ReportFeedbackPanel({ feedbackId }: { feedbackId: number | null | undefined }) {
  const [score, setScore] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [saveExample, setSaveExample] = useState(true);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const ids = { title: useId(), comment: useId(), example: useId() };

  if (typeof feedbackId !== "number") {
    return (
      <section className="report-feedback-panel" aria-labelledby={ids.title}>
        <strong id={ids.title}>{tr("interface.report_feedback_title")}</strong>
        <small className="report-feedback-status">{tr("interface.report_feedback_not_ratable")}</small>
      </section>
    );
  }

  if (status.kind === "saved") return null;

  const submit = async () => {
    if (score === null) return;
    setStatus({ kind: "saving" });
    try {
      await api.rateReport(feedbackId, score, comment, score >= EXAMPLE_MIN_SCORE && saveExample);
      setStatus({ kind: "saved" });
    } catch (error) {
      setStatus({ kind: "failed", message: errorMessage(error, tr("interface.report_feedback_failed")) });
    }
  };
  const edit = () => { if (status.kind !== "saving") setStatus({ kind: "idle" }); };

  return (
    <section className="report-feedback-panel" aria-labelledby={ids.title}>
      <strong id={ids.title}>{tr("interface.report_feedback_title")}</strong>
      <small className="report-feedback-hint">{tr("interface.report_feedback_hint")}</small>
      <div className="report-feedback-scores" role="group" aria-label={tr("interface.report_feedback_score_label")}>
        {SCORES.map((value) => (
          <button
            key={value}
            type="button"
            className="report-feedback-score"
            aria-pressed={score === value}
            aria-label={tr("interface.report_feedback_score_option", { score: value })}
            onClick={() => { setScore(value); edit(); }}
          >
            {value}
          </button>
        ))}
      </div>
      <label htmlFor={ids.comment}>{tr("interface.report_feedback_comment_label")}</label>
      <textarea
        id={ids.comment}
        className="report-feedback-comment"
        value={comment}
        maxLength={MAX_COMMENT_CHARS}
        rows={3}
        placeholder={tr("interface.report_feedback_comment_placeholder")}
        onChange={(event) => { setComment(event.target.value); edit(); }}
      />
      {score !== null && score >= EXAMPLE_MIN_SCORE && (
        <div className="report-feedback-example">
          <input
            id={ids.example}
            type="checkbox"
            checked={saveExample}
            onChange={(event) => { setSaveExample(event.target.checked); edit(); }}
          />
          <label htmlFor={ids.example}>
            {tr("interface.report_feedback_save_example")}
            <small>{tr("interface.report_feedback_save_example_hint")}</small>
          </label>
        </div>
      )}
      <div className="report-feedback-actions">
        <button
          type="button"
          className="secondary-button"
          disabled={score === null || status.kind === "saving"}
          onClick={() => void submit()}
        >
          {status.kind === "saving" ? tr("interface.report_feedback_saving") : tr("interface.report_feedback_submit")}
        </button>
        <small className="report-feedback-status" role="status" aria-live="polite">
          {status.kind === "failed" && status.message}
        </small>
      </div>
    </section>
  );
}
