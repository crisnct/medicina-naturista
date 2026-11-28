import { getLanguage, tr, type Language } from "../lib/texts";
import type {
  CategoriesResponse,
  ClassificationResponse,
  ConditionResponse,
  EmbeddingModelStatus,
  HerbEvidencePage,
  LocalModelRuntime,
  LocalModelsState,
  LearningState,
  HerbEvidenceKind,
  HerbSafetyPage,
  HerbSafetyEvidencePage,
  ReportGeneration,
  MessagesResponse,
  GenerationLimits,
  ReportEffort,
  ReportModel,
  ReportModelsResponse,
  ReportBatchEstimate,
  ReportDurationEstimate,
  ReportOutputRecommendation,
  SearchSignals,
  SendMessageResponse,
  SessionResponse,
  StartupStatus,
  ResourceDecision,
} from "./types";
import { claimTab, releaseTab } from "../lib/tabLease";

// Each loaded document owns a new conversation, including after a hard reload.
// Keep the identity in memory so retries within this page use the same session.
let tabId = crypto.randomUUID();
// Unload requests still identify their document, so delayed cleanup cannot
// close another document's session.
const PAGE_ID = crypto.randomUUID();
let sessionAdmitted = false;

function getTabId(): string {
  return tabId;
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public code?: string, public retryAfter?: number) {
    super(message);
    this.name = "ApiError";
  }
}

// Vite's own base path (PUBLIC_BASE_PATH at build time — see vite.config.ts),
// e.g. "/medicina/" behind the nginx/Caddy sub-path deployment, or "/" at the
// domain root. Every API call must be prefixed with it too: unlike asset URLs
// (which Vite rewrites automatically), a hand-written fetch("/api/...") is an
// absolute path from the DOMAIN root, not from the app's own mount point — it
// would reach the reverse proxy's root location instead of this app's.
const API_BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

export function herbImageUrl(herbId: number): string {
  return `${API_BASE}/api/herb-images/${herbId}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-App-Language": getLanguage(),
      "X-Tab-Id": getTabId(),
      "X-Page-Id": PAGE_ID,
      // Harmless everywhere else; tells an ngrok free-tier tunnel (used for
      // quick live testing) to skip its browser-warning interstitial for
      // fetch/XHR calls instead of returning its own 401 in front of the app.
      "ngrok-skip-browser-warning": "true",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    const message = typeof detail === "string" ? detail : detail?.message;
    throw new ApiError(response.status, message ?? tr("interface.api_unexpected_error"), detail?.code, Number(response.headers.get("Retry-After")) || undefined);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  changeLanguage: (language: Language) => request<{ language: Language }>("/api/language", { method: "POST", headers: { "X-App-Language": language } }),
  getStartup: () => request<StartupStatus>("/api/startup", { signal: AbortSignal.timeout(10000) }),
  getSession: async () => {
    while (!await claimTab(getTabId())) {
      tabId = crypto.randomUUID();
    }
    try {
      const session = await request<SessionResponse>("/api/session");
      sessionAdmitted = true;
      return session;
    } catch (error) {
      if (!sessionAdmitted) releaseTab();
      throw error;
    }
  },
  // The language is the one the caller means, not the current one: refetching a cached entry of
  // another language must not return the current language's tree.
  getCategories: (language?: Language) =>
    request<CategoriesResponse>("/api/categories", language ? { headers: { "X-App-Language": language } } : undefined),
  getHerbEvidence: (groupId: string, conditionId: number | null, offset: number, signal: AbortSignal, evidenceKind: HerbEvidenceKind = "positive") => {
    const query = new URLSearchParams({ offset: String(offset) });
    if (evidenceKind !== "positive") query.set("evidenceKind", evidenceKind);
    if (conditionId !== null) query.set("conditionId", String(conditionId));
    return request<HerbEvidencePage>(`/api/herb-evidence/${encodeURIComponent(groupId)}?${query}`, { signal });
  },
  getReportModels: () => request<ReportModelsResponse>("/api/report-models"),
  getHerbSafety: (groupId: string, offset: number, signal: AbortSignal) =>
    request<HerbSafetyPage>(`/api/herb-safety/${encodeURIComponent(groupId)}?${new URLSearchParams({ offset: String(offset) })}`, { signal }),
  getHerbSafetyEvidence: (groupId: string, warningId: string, offset: number, signal: AbortSignal) =>
    request<HerbSafetyEvidencePage>(`/api/herb-safety/${encodeURIComponent(groupId)}/evidence?${new URLSearchParams({ warningId, offset: String(offset) })}`, { signal }),
  getReportDurationEstimate: (model: ReportModel, characters: number, signal: AbortSignal, effort?: ReportEffort) =>
    request<ReportDurationEstimate>(`/api/report-duration-estimate?${new URLSearchParams({ model, characters: String(characters), ...(effort ? { effort } : {}) })}`, {
      signal: AbortSignal.any([signal, AbortSignal.timeout(5000)]),
    }),
  getReportOutputRecommendation: (model: ReportModel, effort: ReportEffort | undefined, signal: AbortSignal) =>
    request<ReportOutputRecommendation>(`/api/report-output-recommendation?${new URLSearchParams({ model, ...(effort ? { effort } : {}) })}`, {
      signal: AbortSignal.any([signal, AbortSignal.timeout(5000)]),
    }),
  getReportBatchEstimate: (searchId: string, minScore: number, model: ReportModel, effort: ReportEffort | undefined, limits: Partial<GenerationLimits> | undefined, signal: AbortSignal) => {
    const query = new URLSearchParams({ model, minScore: String(minScore) });
    if (effort) query.set("effort", effort);
    if (limits?.batchMaxChars !== undefined) query.set("batchMaxChars", String(limits.batchMaxChars));
    if (limits?.batchWorkers !== undefined) query.set("batchWorkers", String(limits.batchWorkers));
    if (limits?.maxOutputTokens !== undefined) query.set("maxOutputTokens", String(limits.maxOutputTokens));
    if (limits?.thinkingTokens !== undefined) query.set("thinkingTokens", String(limits.thinkingTokens));
    return request<ReportBatchEstimate>(`/api/searches/${encodeURIComponent(searchId)}/report-batches?${query}`, {
      signal: AbortSignal.any([signal, AbortSignal.timeout(10000)]),
    });
  },
  sendMessage: (message: string, categories: string[], signals: SearchSignals) =>
    request<SendMessageResponse>("/api/messages", {
      method: "POST",
      body: JSON.stringify({ message, categories, signals, messageId: crypto.randomUUID() }),
    }),
  // Classify the accepted message before any content search or external delivery.
  // After loadClassifierModel the chat asks again with modelLoaded, so the server goes on whatever
  // the load did.
  classifyMessage: (revision: number, modelLoaded = false) => request<ClassificationResponse>("/api/classify", {
    method: "POST",
    headers: { "X-Context-Revision": String(revision), ...(modelLoaded ? { "X-Classifier-Model-Loaded": "1" } : {}) },
  }),
  // Whether Ollama holds the local classifier, and its load (it leaves after the message's last call).
  getClassifierModel: () => request<EmbeddingModelStatus>("/api/classifier-model"),
  loadClassifierModel: () => request<EmbeddingModelStatus>("/api/classifier-model/load", { method: "POST" }),
  // Asks the AI for the condition the dictionary does not know; only called
  // when classifyMessage() said identifyCondition. Its startSearch says whether
  // the retrieval should follow.
  identifyCondition: (revision?: number) => request<ConditionResponse>("/api/condition", {
    method: "POST", headers: revision === undefined ? {} : { "X-Context-Revision": String(revision) },
  }),
  // Slower retrieval step for the health problem/categories the previous
  // message/classification calls stored on the session, when routing permits it.
  // Before a semantic search: whether Ollama holds the question model, and loading it when it does
  // not, so the chat can say why the first question after an Ollama restart waits.
  getEmbeddingModel: () => request<EmbeddingModelStatus>("/api/embedding-model"),
  loadEmbeddingModel: () => request<EmbeddingModelStatus>("/api/embedding-model/load", { method: "POST" }),
  // The admin's unload of one model from the window; answers the window's fresh state.
  unloadLocalModel: (runtime: LocalModelRuntime, id: string) => request<LocalModelsState>("/api/local-models/unload", {
    method: "POST", body: JSON.stringify({ runtime, id }),
  }),
  // The local AI models in memory and their RAM/VRAM split, for the floating window.
  getLocalModels: (signal?: AbortSignal) => request<LocalModelsState>("/api/local-models", {
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000),
  }),
  // The admin's multilevel learning: the levels' state, and a start or stop of one level or all.
  getLearning: (signal?: AbortSignal) => request<LearningState>("/api/learning", {
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000),
  }),
  startLearning: (level: number | null, includeLower = false) => request<LearningState>("/api/learning/start", {
    method: "POST",
    body: JSON.stringify(level === null ? { all: true } : { level, include_lower: includeLower }),
    // A start may first stop an idle vLLM report server to free the GPU.
    signal: AbortSignal.timeout(60000),
  }),
  stopLearning: (level: number | null) => request<LearningState>("/api/learning/stop", {
    method: "POST",
    body: JSON.stringify(level === null ? { all: true } : { level }),
    signal: AbortSignal.timeout(30000),
  }),
  search: (revision?: number) => request<MessagesResponse>("/api/search", {
    method: "POST", headers: revision === undefined ? {} : { "X-Context-Revision": String(revision) },
  }),
  // minScore: only fragments whose relevance percent reaches it go to the AI (0 = all).
  generateReport: (searchId: string, minScore: number, model: ReportModel = "ollama-gemma4:12b", requestId: string = crypto.randomUUID(), effort: ReportEffort = "low", limits?: GenerationLimits) =>
    request<ReportGeneration>(`/api/searches/${encodeURIComponent(searchId)}/generate`, {
      method: "POST",
      body: JSON.stringify({ minScore, model, effort, requestId, ...limits }),
      signal: AbortSignal.timeout(15000),
    }),
  getGeneration: (jobId: string, signal?: AbortSignal) => request<ReportGeneration>(`/api/report-generations/${encodeURIComponent(jobId)}`, {
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000),
  }),
  cancelGeneration: (jobId: string) => request<ReportGeneration>(`/api/report-generations/${encodeURIComponent(jobId)}/cancel`, {
    method: "POST", signal: AbortSignal.timeout(15000),
  }),
  // The answer to the memory test a Colibri job waits on; giving up is cancelGeneration.
  decideResources: ({ jobId, decision }: { jobId: string; decision: ResourceDecision }) =>
    request<ReportGeneration>(`/api/report-generations/${encodeURIComponent(jobId)}/resource-decision`, {
      method: "POST", body: JSON.stringify({ decision }), signal: AbortSignal.timeout(15000),
    }),
  // The admin's rating of a published report; each call replaces the previous one.
  rateReport: (feedbackId: number, score: number, comment: string, saveExample: boolean) =>
    request<void>(`/api/reports/${feedbackId}/feedback`, {
      method: "POST",
      body: JSON.stringify({ score, comment, save_example: saveExample }),
      signal: AbortSignal.timeout(15000),
    }),
  endSession: () => request<MessagesResponse>("/api/session/end", { method: "POST" }),
  // keepalive fetch (not navigator.sendBeacon, which can't carry the X-Tab-Id
  // header) so the request has a chance to complete after the page unloads.
  unloadSession: () => {
    if (sessionAdmitted) {
      sessionAdmitted = false;
      void request("/api/session/unload", { method: "POST", keepalive: true }).catch(() => {});
    }
    releaseTab();
  },
};

export function errorMessage(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback;
  if (error.code === "APP_INITIALIZING") return error.message;
  if (error.status === 413) return tr("interface.api_request_too_large");
  if (error.status === 429) {
    if (error.code === "GENERATION_CAPACITY" || error.code === "GENERATION_QUEUE_FULL" || error.code === "GENERATION_HISTORY_LIMIT" || error.code === "OPERATION_LIMIT") return error.message;
    if (error.code === "RATE_LIMIT" && error.retryAfter) return tr("interface.api_retry_after", { retry_after: error.retryAfter });
    return tr("interface.api_rate_limited");
  }
  if (error.status === 409) return error.message;
  if (error.code?.startsWith("INDEX_")) return tr("interface.api_index_maintenance");
  if (error.code === "OWNER_AUTH_UNAVAILABLE") return tr("interface.api_authorization_unavailable");
  if (error.code === "POSITIVE_RANKING_NOT_READY") return tr("interface.api_positive_ranking_not_ready");
  if (error.code === "POSITIVE_RANKING_STALE") return tr("interface.api_positive_ranking_stale");
  if (error.status === 503) return tr("interface.api_service_unavailable");
  return error.message;
}

export function isSessionUnavailable(error: unknown): boolean {
  return error instanceof ApiError && (
    error.status === 401 || error.code === "SESSION_EXPIRED" || error.code === "SESSION_CLOSED"
  );
}
