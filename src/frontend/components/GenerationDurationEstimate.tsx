import { tr } from "../lib/texts";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ReportDurationEstimate, ReportEffort, ReportModel } from "../api/types";

export function GenerationDurationEstimate({
  model,
  effort,
  characters,
  refreshKey,
}: {
  model: ReportModel;
  // Undefined for models without an effort control.
  effort?: ReportEffort;
  characters?: number;
  refreshKey?: string;
}) {
  const key = JSON.stringify([model, effort, characters, refreshKey]);
  const [result, setResult] = useState<{ key: string; data: ReportDurationEstimate | null }>();

  useEffect(() => {
    if (characters === undefined || characters === 0) return;
    const controller = new AbortController();
    let current = true;
    const requestKey = JSON.stringify([model, effort, characters, refreshKey]);
    api.getReportDurationEstimate(model, characters, controller.signal, effort).then((data) => {
      if (data.model !== model || data.characters !== characters) throw new Error("Unexpected estimate inputs");
      if (current) setResult({ key: requestKey, data });
    }).catch(() => {
      if (current && !controller.signal.aborted) setResult({ key: requestKey, data: null });
    });
    return () => { current = false; controller.abort(); };
  }, [model, effort, characters, refreshKey]);

  const data = result?.key === key ? result.data : undefined;
  let value = tr("interface.estimate_loading");
  let explanation: string | undefined;
  if (characters === undefined) value = tr("interface.estimate_pending");
  else if (characters === 0) value = "00:00";
  else if (data === null) value = tr("interface.estimate_temporarily_unavailable");
  else if (data !== undefined) {
    const seconds = data.estimatedSeconds;
    if (seconds === null || !Number.isSafeInteger(seconds) || seconds < 0) {
      value = tr("interface.estimate_unavailable");
      explanation = tr("interface.estimate_no_samples");
    } else {
      value = `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}`;
      explanation = tr("interface.estimate_sample_hint", { sample_count: data.sampleCount });
    }
  }

  return (
    <p className="eligible-count report-duration-estimate" aria-live="polite" title={explanation}>
      {tr("interface.estimate_prefix")}<strong>{value}</strong>{/^\d+:\d{2}$/.test(value) ? tr("interface.estimate_units") : ""}
    </p>
  );
}
