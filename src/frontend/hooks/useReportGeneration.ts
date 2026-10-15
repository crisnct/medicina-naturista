import { useEffect, useRef, type Dispatch, type SetStateAction } from "react";
import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, errorMessage, isSessionUnavailable } from "../api/client";
import type { ReportGeneration, ReportModel, SessionResponse } from "../api/types";
import type { GenerationFeedback } from "../lib/generationFeedback";
import { AI_ACTIVITY_LABELS } from "../lib/generationFeedback";

const SESSION_KEY = ["session"] as const;
export const activeGeneration = (job: ReportGeneration) => job.state === "accepted" || job.state === "running";
const observingGeneration = (job: ReportGeneration) => activeGeneration(job) || job.workerActive === true;
const stages: Record<string, string> = {
  queued: "Raportul așteaptă în coadă",
  preparing: "Pregătesc datele", generating: "Redactez raportul", validating: "Verific recomandările",
  rendering_pdf: "Creez PDF-ul", publishing: "Salvez raportul",
};
const stageOrder = Object.keys(stages);

function currentGeneration(sessionJob: ReportGeneration, polledJob?: ReportGeneration): ReportGeneration {
  if (!polledJob || polledJob.jobId !== sessionJob.jobId) return sessionJob;
  // Session refreshes and job polling can complete in either order. A terminal
  // session snapshot must not be replaced by an older active job cache entry.
  if (!activeGeneration(sessionJob)) {
    if (activeGeneration(polledJob) || sessionJob.workerActive === false) return sessionJob;
  }
  if (activeGeneration(sessionJob) && activeGeneration(polledJob)
    && stageOrder.indexOf(sessionJob.stage) > stageOrder.indexOf(polledJob.stage)) return sessionJob;
  return polledJob;
}
const transient = (error: unknown) => !(error instanceof ApiError)
  || [502, 503, 504].includes(error.status)
  || (error.status === 429 && error.code === "RATE_LIMIT");

export function useReportGeneration(
  session: SessionResponse | undefined,
  setFeedback: Dispatch<SetStateAction<Record<string, GenerationFeedback>>>,
  setNeedsRecovery: Dispatch<SetStateAction<boolean>>,
  setBanner: Dispatch<SetStateAction<string | null>>,
) {
  const client = useQueryClient();
  const handled = useRef(new Set<string>());
  const blocked = useRef(new Set<string>());
  const activitySnapshots = useRef(new Map<string, { updatedAt: number; receivedAt: number }>());
  const jobs = session?.generations ?? [];
  const update = (job: ReportGeneration) => client.setQueryData<SessionResponse>(SESSION_KEY, (old) => old ? {
    ...old, generations: [...(old.generations ?? []).filter((item) => item.jobId !== job.jobId), job],
  } : old);
  const queries = useQueries({ queries: jobs.map((job) => ({
    queryKey: ["report-generation", job.jobId],
    queryFn: ({ signal }: { signal: AbortSignal }) => api.getGeneration(job.jobId, signal),
    initialData: job,
    enabled: observingGeneration(currentGeneration(job, client.getQueryData<ReportGeneration>(["report-generation", job.jobId]))) && !blocked.current.has(job.jobId),
    retry: false,
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
    refetchInterval: (query: { state: { data: ReportGeneration | undefined; error: Error | null; fetchFailureCount: number; errorUpdateCount: number } }) => {
      if (!query.state.data || !observingGeneration(currentGeneration(job, query.state.data)) || (query.state.error && !transient(query.state.error))) return false;
      return query.state.error ? Math.min(15000, 3000 * 2 ** Math.min(query.state.errorUpdateCount, 3)) : 3000;
    },
  })) });

  const cancel = useMutation({
    mutationFn: api.cancelGeneration,
    onSuccess: (job) => { client.setQueryData(["report-generation", job.jobId], job); update(job); },
    onError: (error) => setBanner(errorMessage(error, "Anularea nu a putut fi confirmată. Verificați din nou starea.")),
  });

  const observed = queries.map((query, index) => currentGeneration(jobs[index], query.data));

  useEffect(() => {
    queries.forEach((query, index) => {
      const job = observed[index];
      if (!job) return;
      if (!observingGeneration(job)) blocked.current.delete(job.jobId);
      if (query.error && observingGeneration(job)) {
        if (query.error instanceof ApiError && query.error.code === "MODEL_FORBIDDEN" && !blocked.current.has(job.jobId)) {
          void client.invalidateQueries({ queryKey: ["report-models"] });
        }
        const fatal = !transient(query.error);
        if (fatal) blocked.current.add(job.jobId);
        if (isSessionUnavailable(query.error)) setNeedsRecovery(true);
        setFeedback((old) => {
          const message = fatal ? errorMessage(query.error, "Generarea nu mai este disponibilă.") : "Conexiunea este întreruptă. Verific din nou starea raportului.";
          return old[job.searchId]?.message === message ? old : { ...old, [job.searchId]: { message, progress: fatal ? undefined : message } };
        });
        return;
      }
      if (observingGeneration(job)) return;
      if (handled.current.has(job.jobId)) return;
      handled.current.add(job.jobId);
      if (jobs.filter((item) => item.searchId === job.searchId).at(-1)?.jobId !== job.jobId) return;
      if (job.partial) setBanner("Raportul este parțial: unele recomandări nu au putut fi validate.");
      if (job.state !== "succeeded") setFeedback((old) => ({ ...old, [job.searchId]: { message: job.message ?? "Raportul nu a putut fi generat." } }));
      else setFeedback((old) => { if (!old[job.searchId]) return old; const next = { ...old }; delete next[job.searchId]; return next; });
      // Read canonical history, never append a terminal result more than once.
      void api.getSession().then((fresh) => client.setQueryData(SESSION_KEY, fresh)).catch((error: unknown) => {
        setBanner(errorMessage(error, "Raportul a fost procesat, dar conversația nu a putut fi sincronizată. Reîncărcați pagina."));
      });
    });
  });

  const start = useMutation({
    mutationFn: async ({ searchId, minScore, model, requestId }: { searchId: string; minScore: number; model: ReportModel; requestId: string }) => {
      const job = await api.generateReport(searchId, minScore, model, requestId);
      if (!job.jobId || !job.state) throw new ApiError(409, "Versiunea aplicației s-a schimbat. Reîncărcați pagina.", "API_CONTRACT_CHANGED");
      return job;
    },
    // Reuse requestId if the admission response was lost in transit.
    retry: (count, error) => count < 1 && transient(error),
    retryDelay: (count, error) => error instanceof ApiError && error.status === 429
      ? Math.max(1, error.retryAfter ?? 5) * 1000
      : Math.min(1000 * 2 ** count, 10000),
    onSuccess: (job) => {
      sessionStorage.removeItem(`report-request:${job.searchId}`);
      setFeedback((old) => { const next = { ...old }; delete next[job.searchId]; return next; });
      update(job);
    },
    onError: (error, { searchId }) => {
      if (error instanceof ApiError && error.status < 500) sessionStorage.removeItem(`report-request:${searchId}`);
      if (error instanceof ApiError && error.status === 403) void client.invalidateQueries({ queryKey: ["report-models"] });
      if (isSessionUnavailable(error)) setNeedsRecovery(true);
      setFeedback((old) => ({ ...old, [searchId]: { message: errorMessage(error, "Pornirea nu a putut fi confirmată. Încercați din nou cu aceleași opțiuni."), requiresAuthorization: error instanceof ApiError && error.status === 403 } }));
      // Recover an admitted job even when both admission responses were lost.
      void api.getSession().then((fresh) => client.setQueryData(SESSION_KEY, fresh)).catch(() => {});
    },
  });
  const feedback: Record<string, GenerationFeedback> = {};
  const latestJobBySearch = new Map(jobs.map((job) => [job.searchId, job.jobId]));
  for (const [index, job] of observed.entries()) {
    if (latestJobBySearch.get(job.searchId) !== job.jobId) continue;
    if (job.state === "succeeded" && job.streamPreview && !blocked.current.has(job.jobId)) {
      feedback[job.searchId] = { message: "", streamPreview: job.streamPreview, completed: true };
      continue;
    }
    if (!observingGeneration(job) || blocked.current.has(job.jobId)) continue;
    const updatedAt = queries[index]?.dataUpdatedAt ?? 0;
    let snapshot = activitySnapshots.current.get(job.jobId);
    if (!snapshot || snapshot.updatedAt !== updatedAt) {
      snapshot = { updatedAt, receivedAt: performance.now() };
      activitySnapshots.current.set(job.jobId, snapshot);
    }
    const aiActivity = activeGeneration(job) && job.stage === "generating" && !queries[index]?.error
      ? job.aiActivity : undefined;
    feedback[job.searchId] = {
      message: "", progress: !activeGeneration(job) ? "Generarea a fost oprită. Aștept închiderea apelului AI…" : queries[index]?.error ? "Conexiunea este întreruptă. Verific din nou starea raportului." : job.stage === "queued" && job.queuePosition ? `Raportul așteaptă în coadă. Poziția: ${job.queuePosition}. Va porni automat.` : (aiActivity ? AI_ACTIVITY_LABELS[aiActivity.phase] : undefined) ?? stages[job.stage] ?? "Pregătesc raportul",
      cancel: activeGeneration(job) ? () => cancel.mutate(job.jobId) : undefined,
      streamPreview: job.streamPreview,
      thinkingPreview: job.thinkingPreview,
      aiActivity,
      activityReceivedAt: snapshot.receivedAt,
    };
  }
  const activeSearches = new Set(observed.filter((job) => observingGeneration(job) && !blocked.current.has(job.jobId)).map((job) => job.searchId));
  if (start.isPending && start.variables) {
    const searchId = start.variables.searchId;
    activeSearches.add(searchId);
    feedback[searchId] = {
      message: "",
      progress: "Solicit pornirea raportului…",
    };
  }
  return {
    feedback,
    activeSearches,
    isGenerating: start.isPending || observed.some((job) => observingGeneration(job) && !blocked.current.has(job.jobId)),
    generate: (searchId: string, minScore: number, model: ReportModel) => {
      const fingerprint = JSON.stringify({ minScore, model });
      const key = `report-request:${searchId}`;
      let saved: { fingerprint: string; requestId: string } | null = null;
      try { saved = JSON.parse(sessionStorage.getItem(key) ?? "null"); } catch { /* Ignore malformed stale storage. */ }
      const requestId = saved?.fingerprint === fingerprint ? saved.requestId : crypto.randomUUID();
      sessionStorage.setItem(key, JSON.stringify({ fingerprint, requestId }));
      start.mutate({ searchId, minScore, model, requestId });
    },
  };
}
