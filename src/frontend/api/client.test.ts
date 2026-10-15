import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

beforeEach(() => {
  vi.resetModules();
  window.sessionStorage.clear();
  vi.stubGlobal("sessionStorage", window.sessionStorage);
});

afterEach(async () => {
  (await import("../lib/tabLease")).releaseTab();
  vi.unstubAllGlobals();
});

describe("tab ownership", () => {
  it("opens a duplicated tab with its own session and unloads only that session", async () => {
    sessionStorage.setItem("naturist_tab_id", "original-tab");
    const lockRequest = vi.fn(async (name: string, _options: unknown, callback: (lock: Lock | null) => Promise<void>) =>
      callback(name === "naturist-tab:original-tab" ? null : { name, mode: "exclusive" }));
    vi.stubGlobal("navigator", { locks: { request: lockRequest } });
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ history: [] })))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetch);
    const { api } = await import("./client");
    await expect(api.getSession()).resolves.toEqual({ history: [] });
    const newTabId = sessionStorage.getItem("naturist_tab_id");
    expect(newTabId).toBeTruthy();
    expect(newTabId).not.toBe("original-tab");
    expect(lockRequest).toHaveBeenCalledTimes(2);
    expect(fetch).toHaveBeenLastCalledWith(expect.stringContaining("/api/session"), expect.objectContaining({
      headers: expect.objectContaining({ "X-Tab-Id": newTabId }),
    }));
    api.unloadSession();
    expect(fetch).toHaveBeenLastCalledWith(expect.stringContaining("/api/session/unload"), expect.objectContaining({
      method: "POST", keepalive: true, headers: expect.objectContaining({ "X-Tab-Id": newTabId }),
    }));
  });

  it("keeps the stored session ID when no other tab holds it", async () => {
    sessionStorage.setItem("naturist_tab_id", "reloaded-tab");
    const lockRequest = vi.fn(async (name: string, _options: unknown, callback: (lock: Lock | null) => Promise<void>) => callback({ name, mode: "exclusive" }));
    vi.stubGlobal("navigator", { locks: { request: lockRequest } });
    const fetch = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ history: [] })));
    vi.stubGlobal("fetch", fetch);
    const { api } = await import("./client");
    await api.getSession();
    await api.getSession();
    expect(lockRequest).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem("naturist_tab_id")).toBe("reloaded-tab");
    for (const [, init] of fetch.mock.calls) {
      expect(init.headers["X-Tab-Id"]).toBe("reloaded-tab");
    }
  });

  it("releases a server-rejected tab without unloading it and allows retry", async () => {
    const lockRequest = vi.fn(async (name: string, _options: unknown, callback: (lock: Lock | null) => Promise<void>) => callback({ name, mode: "exclusive" }));
    vi.stubGlobal("navigator", { locks: { request: lockRequest } });
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: { code: "GLOBAL_SESSION_LIMIT", message: "Capacitatea aplicației este ocupată." } }), { status: 503 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ history: [] })))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetch);
    const { api } = await import("./client");
    await expect(api.getSession()).rejects.toMatchObject({ code: "GLOBAL_SESSION_LIMIT" });
    api.unloadSession();
    expect(fetch).toHaveBeenCalledTimes(1);
    await expect(api.getSession()).resolves.toEqual({ history: [] });
    expect(lockRequest).toHaveBeenCalledTimes(2);
    api.unloadSession();
    expect(fetch).toHaveBeenLastCalledWith(expect.stringContaining("/api/session/unload"), expect.objectContaining({ method: "POST", keepalive: true }));
  });
});
