import { tr } from "../lib/texts";
import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { GenerationLimits, ReportBatchEstimate, ReportEffort, ReportModel } from "../api/types";

// Typing in a limit field must not ask the server for a count on every keystroke.
const TYPING_DELAY_MS = 400;

export function GenerationBatchEstimate({
  searchId,
  minScore,
  model,
  effort,
  limits,
  eligibleCount,
  valid = true,
}: {
  searchId: string;
  minScore: number;
  model: ReportModel;
  // Undefined for models without an effort control.
  effort?: ReportEffort;
  // The admin's typed limits; undefined keeps the configured ones.
  limits?: Pick<GenerationLimits, "batchMaxTokens" | "batchWorkers" | "maxOutputTokens">;
  // Undefined while the search's fragments are unknown to the page.
  eligibleCount?: number;
  // False while a typed limit is not a usable number.
  valid?: boolean;
}) {
  const key = JSON.stringify([searchId, minScore, model, effort, limits]);
  const [result, setResult] = useState<{ key: string; data: ReportBatchEstimate | null; error?: string }>();
  const ask = valid && eligibleCount !== undefined && eligibleCount > 0;

  useEffect(() => {
    if (!ask) return;
    const controller = new AbortController();
    let current = true;
    const timer = setTimeout(() => {
      api.getReportBatchEstimate(searchId, minScore, model, effort, limits, controller.signal).then((data) => {
        if (data.searchId !== searchId) throw new Error("Unexpected estimate inputs");
        if (current) setResult({ key, data });
      }).catch((error: unknown) => {
        // The server states why it refuses the limits (HTTP 422); other failures stay generic.
        if (current && !controller.signal.aborted) {
          setResult({ key, data: null, error: error instanceof ApiError && error.status === 422 ? error.message : undefined });
        }
      });
    }, TYPING_DELAY_MS);
    return () => { current = false; clearTimeout(timer); controller.abort(); };
    // `key` carries every input; the objects it was built from change identity on each render.
  }, [ask, key]);

  let value: string;
  if (eligibleCount === undefined) value = tr("interface.generate_count_pending");
  else if (eligibleCount === 0) value = "0";
  else if (!valid) value = "–";
  else if (result?.key !== key) value = tr("interface.estimate_loading");
  else if (result.data === null) value = tr("interface.estimate_temporarily_unavailable");
  else value = String(result.data.batches);
  const data = ask && result?.key === key ? result.data : null;
  const warning = data !== null && data.oversizedBatches > 0
    ? tr("interface.generate_batches_oversized", { count: data.oversizedBatches }) : undefined;

  const error = ask && result?.key === key ? result.error : undefined;
  return (
    <>
      <p className="eligible-count" aria-live="polite" title={tr("interface.generate_batches_hint")}>
        {tr("interface.generate_batches_prefix")}<strong>{value}</strong>
      </p>
      {(error ?? warning) && <p className="generate-recipe-warning" role="status">{error ?? warning}</p>}
    </>
  );
}
