import type {
  CategoriesResponse,
  ConditionResponse,
  GenerateResponse,
  MessagesResponse,
  SearchSignals,
  SendMessageResponse,
  SessionResponse,
} from "./types";

const TAB_ID_KEY = "naturist_tab_id";

// One id per browser tab, generated once and kept in sessionStorage (not
// localStorage, so separate tabs stay isolated — the same "one session per
// browser tab" guarantee Gradio used to give us for free via its own
// per-connection request.session_hash).
function getTabId(): string {
  let tabId = sessionStorage.getItem(TAB_ID_KEY);
  if (!tabId) {
    tabId = crypto.randomUUID();
    sessionStorage.setItem(TAB_ID_KEY, tabId);
  }
  return tabId;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
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
      // Harmless everywhere else; tells an ngrok free-tier tunnel (used for
      // quick live testing) to skip its browser-warning interstitial for
      // fetch/XHR calls instead of returning its own 401 in front of the app.
      "ngrok-skip-browser-warning": "true",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, body?.detail ?? "A apărut o eroare neașteptată. Încercați din nou.");
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  getSession: () => request<SessionResponse>("/api/session"),
  getCategories: () => request<CategoriesResponse>("/api/categories"),
  sendMessage: (message: string, categories: string[], signals: SearchSignals) =>
    request<SendMessageResponse>("/api/messages", {
      method: "POST",
      body: JSON.stringify({ message, categories, signals }),
    }),
  // Asks the AI for the condition the dictionary does not know; only called
  // when sendMessage() said identifyCondition. Its startSearch says whether
  // the retrieval should follow.
  identifyCondition: () => request<ConditionResponse>("/api/condition", { method: "POST" }),
  // Slower retrieval step for the health problem/categories the previous
  // sendMessage() call already stored on the session — only called when
  // that call's startSearch flag says so.
  search: () => request<MessagesResponse>("/api/search", { method: "POST" }),
  generateReport: (searchId: string) =>
    request<GenerateResponse>(`/api/searches/${encodeURIComponent(searchId)}/generate`, { method: "POST" }),
  endSession: () => request<MessagesResponse>("/api/session/end", { method: "POST" }),
  // keepalive fetch (not navigator.sendBeacon, which can't carry the X-Tab-Id
  // header) so the request has a chance to complete after the page unloads.
  unloadSession: () => {
    void request("/api/session/unload", { method: "POST", keepalive: true }).catch(() => {});
  },
};
