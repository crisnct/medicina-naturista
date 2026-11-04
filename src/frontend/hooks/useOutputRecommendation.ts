import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ReportEffort, ReportModel } from "../api/types";

export interface OutputRecommendation {
  // Undefined until enough reports were measured for the model and effort.
  tokens?: number;
  sampleCount: number;
}

// The per-batch output limit that reports of this model and effort have been seen to need.
// `refreshKey` asks again after a generation, which adds a measurement.
export function useOutputRecommendation(
  model: ReportModel,
  effort: ReportEffort | undefined,
  enabled: boolean,
  refreshKey?: string,
): OutputRecommendation | undefined {
  const key = JSON.stringify([model, effort, refreshKey]);
  const [result, setResult] = useState<{ key: string; data: OutputRecommendation }>();

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    let current = true;
    api.getReportOutputRecommendation(model, effort, controller.signal).then((data) => {
      if (data.model !== model) throw new Error("Unexpected recommendation inputs");
      if (current) setResult({ key, data: { tokens: data.recommendedTokens ?? undefined, sampleCount: data.sampleCount } });
    }).catch(() => {
      // A missing recommendation only means nothing is advised.
      if (current && !controller.signal.aborted) setResult({ key, data: { sampleCount: 0 } });
    });
    return () => { current = false; controller.abort(); };
  }, [enabled, key]);

  return enabled && result?.key === key ? result.data : undefined;
}
