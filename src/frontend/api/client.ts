import type {
  CategoriesResponse,
  ClassificationResponse,
  ConditionResponse,
  ReportGeneration,
  MessagesResponse,
  ReportModel,
  ReportModelsResponse,
  ReportDurationEstimate,
  SearchSignals,
  SendMessageResponse,
  SessionResponse,
  StartupStatus,
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
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
    throw new ApiError(response.status, message ?? "A apărut o eroare neașteptată. Încercați din nou.", detail?.code, Number(response.headers.get("Retry-After")) || undefined);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
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
  getCategories: () => request<CategoriesResponse>("/api/categories"),
  getReportModels: () => request<ReportModelsResponse>("/api/report-models"),
  getReportDurationEstimate: (model: ReportModel, characters: number, signal: AbortSignal) =>
    request<ReportDurationEstimate>(`/api/report-duration-estimate?${new URLSearchParams({ model, characters: String(characters) })}`, {
      signal: AbortSignal.any([signal, AbortSignal.timeout(5000)]),
    }),
  sendMessage: (message: string, categories: string[], signals: SearchSignals) =>
    request<SendMessageResponse>("/api/messages", {
      method: "POST",
      body: JSON.stringify({ message, categories, signals, messageId: crypto.randomUUID() }),
    }),
  // Classify the accepted message before any content search or external delivery.
  classifyMessage: (revision: number) => request<ClassificationResponse>("/api/classify", {
    method: "POST", headers: { "X-Context-Revision": String(revision) },
  }),
  // Asks the AI for the condition the dictionary does not know; only called
  // when classifyMessage() said identifyCondition. Its startSearch says whether
  // the retrieval should follow.
  identifyCondition: (revision?: number) => request<ConditionResponse>("/api/condition", {
    method: "POST", headers: revision === undefined ? {} : { "X-Context-Revision": String(revision) },
  }),
  // Slower retrieval step for the health problem/categories the previous
  // message/classification calls stored on the session, when routing permits it.
  search: (revision?: number) => request<MessagesResponse>("/api/search", {
    method: "POST", headers: revision === undefined ? {} : { "X-Context-Revision": String(revision) },
  }),
  // minScore: only fragments whose relevance percent reaches it go to the AI (0 = all).
  generateReport: (searchId: string, minScore: number, model: ReportModel = "ollama-gemma4:12b", requestId: string = crypto.randomUUID()) =>
    request<ReportGeneration>(`/api/searches/${encodeURIComponent(searchId)}/generate`, {
      method: "POST",
      body: JSON.stringify({ minScore, model, requestId }),
      signal: AbortSignal.timeout(15000),
    }),
  getGeneration: (jobId: string, signal?: AbortSignal) => request<ReportGeneration>(`/api/report-generations/${encodeURIComponent(jobId)}`, {
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000),
  }),
  cancelGeneration: (jobId: string) => request<ReportGeneration>(`/api/report-generations/${encodeURIComponent(jobId)}/cancel`, {
    method: "POST", signal: AbortSignal.timeout(15000),
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
  if (error.status === 413) return "Cererea este prea mare. Reduceți conținutul mesajului.";
  if (error.status === 429) {
    if (error.code === "GENERATION_CAPACITY" || error.code === "GENERATION_QUEUE_FULL" || error.code === "GENERATION_HISTORY_LIMIT" || error.code === "OPERATION_LIMIT") return error.message;
    if (error.code === "RATE_LIMIT" && error.retryAfter) return `Prea multe cereri. Încercați din nou peste ${error.retryAfter} de secunde.`;
    return "Prea multe cereri. Încercați din nou mai târziu.";
  }
  if (error.status === 409) return error.message;
  if (error.code?.startsWith("INDEX_")) return "Indexul este în mentenanță sau necesită resincronizare. Încercați din nou în 60 de secunde.";
  if (error.code === "OWNER_AUTH_UNAVAILABLE") return "Autorizarea este temporar indisponibilă. Încercați mai târziu.";
  if (error.status === 503) return "Serviciul este temporar indisponibil. Încercați mai târziu.";
  return error.message;
}

export function isSessionUnavailable(error: unknown): boolean {
  return error instanceof ApiError && (
    error.status === 401 || error.code === "SESSION_EXPIRED" || error.code === "SESSION_CLOSED"
  );
}
