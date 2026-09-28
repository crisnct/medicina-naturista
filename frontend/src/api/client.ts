import type { CategoriesResponse, GenerateResponse, MessagesResponse, SessionResponse } from "./types";

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-Tab-Id": getTabId(),
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
  sendMessage: (message: string, categories: string[]) =>
    request<MessagesResponse>("/api/messages", {
      method: "POST",
      body: JSON.stringify({ message, categories }),
    }),
  generateReport: (searchId: string) =>
    request<GenerateResponse>(`/api/searches/${encodeURIComponent(searchId)}/generate`, { method: "POST" }),
  endSession: () => request<MessagesResponse>("/api/session/end", { method: "POST" }),
  // keepalive fetch (not navigator.sendBeacon, which can't carry the X-Tab-Id
  // header) so the request has a chance to complete after the page unloads.
  unloadSession: () => {
    void request("/api/session/unload", { method: "POST", keepalive: true }).catch(() => {});
  },
};
