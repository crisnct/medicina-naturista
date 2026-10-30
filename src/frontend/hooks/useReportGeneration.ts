import { tr } from "../lib/texts";
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
  get queued() { return tr("interface.generation_queued_stage"); },
  get preparing() { return tr("interface.generation_prepare_stage"); }, get generating() { return tr("interface.generation_write_stage"); }, get validating() { return tr("interface.generation_validate_stage"); },
  get rendering_pdf() { return tr("interface.generation_pdf_stage"); }, get publishing() { return tr("interface.generation_publish_stage"); },
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
    && (sessionJob.previewVersion ?? 0) > (polledJob.previewVersion ?? 0)) return sessionJob;
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
    onError: (error) => setBanner(errorMessage(error, tr("interface.generation_cancel_failed"))),
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
          const message = fatal ? errorMessage(query.error, tr("common.generation_unavailable")) : tr("interface.generation_connection_lost");
          return old[job.searchId]?.message === message ? old : { ...old, [job.searchId]: { message, progress: fatal ? undefined : message } };
        });
        return;
      }
      if (observingGeneration(job)) return;
      if (handled.current.has(job.jobId)) return;
      handled.current.add(job.jobId);
      if (jobs.filter((item) => item.searchId === job.searchId).at(-1)?.jobId !== job.jobId) return;
      if (job.partial) setBanner(tr("common.partial_report_notice"));
      if (job.state !== "succeeded") setFeedback((old) => ({ ...old, [job.searchId]: { message: job.message ?? tr("interface.generation_failed") } }));
      else setFeedback((old) => { if (!old[job.searchId]) return old; const next = { ...old }; delete next[job.searchId]; return next; });
      // Read canonical history, never append a terminal result more than once.
      void api.getSession().then((fresh) => client.setQueryData(SESSION_KEY, fresh)).catch((error: unknown) => {
        setBanner(errorMessage(error, tr("interface.generation_sync_failed")));
      });
    });
  });

  const start = useMutation({
    mutationFn: async ({ searchId, minScore, model, requestId }: { searchId: string; minScore: number; model: ReportModel; requestId: string }) => {
      const job = await api.generateReport(searchId, minScore, model, requestId);
      if (!job.jobId || !job.state) throw new ApiError(409, tr("interface.generation_contract_changed"), "API_CONTRACT_CHANGED");
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
      setFeedback((old) => ({ ...old, [searchId]: { message: errorMessage(error, tr("interface.generation_start_failed")), requiresAuthorization: error instanceof ApiError && error.status === 403 } }));
      // Recover an admitted job even when both admission responses were lost.
      void api.getSession().then((fresh) => client.setQueryData(SESSION_KEY, fresh)).catch(() => {});
    },
  });
  const feedback: Record<string, GenerationFeedback> = {};
  const latestJobBySearch = new Map(jobs.map((job) => [job.searchId, job.jobId]));
  for (const [index, job] of observed.entries()) {
    if (latestJobBySearch.get(job.searchId) !== job.jobId) continue;
    if (!observingGeneration(job) && !blocked.current.has(job.jobId)) {
      feedback[job.searchId] = {
        message: job.state === "succeeded" ? "" : job.message ?? tr("interface.generation_failed"),
        streamPreview: job.streamPreview,
        reportPreview: job.reportPreview,
        batchesCompleted: job.batchesCompleted,
        batchesTotal: job.batchesTotal,
        batchPreviews: job.batchPreviews,
        thinkingPreview: job.thinkingPreview,
        streamTokensPerSecond: job.streamTokensPerSecond,
        thinkingTokensPerSecond: job.thinkingTokensPerSecond,
        completed: job.state === "succeeded" && Boolean(job.reportPreview ?? job.streamPreview),
        terminal: true,
        generationId: job.jobId,
      };
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
      message: "", progress: !activeGeneration(job) ? tr("interface.generation_stopping") : queries[index]?.error ? tr("interface.generation_connection_lost") : job.stage === "queued" && job.queuePosition ? tr("interface.generation_queue_position", { position: job.queuePosition }) : (aiActivity ? AI_ACTIVITY_LABELS[aiActivity.phase] : undefined) ?? stages[job.stage] ?? tr("interface.generation_preparing"),
      cancel: activeGeneration(job) ? () => cancel.mutate(job.jobId) : undefined,
      generationId: job.jobId,
      generationStartedAt: job.startedAt,
      waitingInQueue: job.state === "accepted" || job.stage === "queued",
      streamPreview: job.streamPreview,
      reportPreview: job.reportPreview,
      batchesCompleted: job.batchesCompleted,
      batchesTotal: job.batchesTotal,
      batchPreviews: job.batchPreviews,
      thinkingPreview: job.thinkingPreview,
      streamTokensPerSecond: job.streamTokensPerSecond,
      thinkingTokensPerSecond: job.thinkingTokensPerSecond,
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
      get progress() { return tr("interface.generation_requesting"); },
      waitingInQueue: true,
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
