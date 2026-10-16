import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ReportDurationEstimate, ReportModel } from "../api/types";

export function GenerationDurationEstimate({
  model,
  characters,
  refreshKey,
}: {
  model: ReportModel;
  characters?: number;
  refreshKey?: string;
}) {
  const key = JSON.stringify([model, characters, refreshKey]);
  const [result, setResult] = useState<{ key: string; data: ReportDurationEstimate | null }>();

  useEffect(() => {
    if (characters === undefined || characters === 0) return;
    const controller = new AbortController();
    let current = true;
    const requestKey = JSON.stringify([model, characters, refreshKey]);
    api.getReportDurationEstimate(model, characters, controller.signal).then((data) => {
      if (data.model !== model || data.characters !== characters) throw new Error("Unexpected estimate inputs");
      if (current) setResult({ key: requestKey, data });
    }).catch(() => {
      if (current && !controller.signal.aborted) setResult({ key: requestKey, data: null });
    });
    return () => { current = false; controller.abort(); };
  }, [model, characters, refreshKey]);

  const data = result?.key === key ? result.data : undefined;
  let value = "se calculează…";
  let explanation: string | undefined;
  if (characters === undefined) value = "se verifică la generare";
  else if (characters === 0) value = "00:00";
  else if (data === null) value = "indisponibilă momentan";
  else if (data !== undefined) {
    const seconds = data.estimatedSeconds;
    if (seconds === null || !Number.isSafeInteger(seconds) || seconds < 0) {
      value = "indisponibilă";
      explanation = "Nu există suficiente măsurători pentru modelul selectat.";
    } else {
      value = `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}`;
      explanation = `Estimare din toate cele ${data.sampleCount} generări înregistrate pentru acest model, fără timpul de așteptare în coadă.`;
    }
  }

  return (
    <p className="eligible-count report-duration-estimate" aria-live="polite" title={explanation}>
      Durată estimată: <strong>{value}</strong>{/^\d+:\d{2}$/.test(value) ? " (min:sec)" : ""}
    </p>
  );
}
