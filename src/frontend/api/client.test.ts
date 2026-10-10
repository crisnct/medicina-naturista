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
  it("rejects a duplicated tab before HTTP and cannot unload the original session", async () => {
    const lockRequest = vi.fn(async (_name: string, _options: unknown, callback: (lock: Lock | null) => Promise<void>) => callback(null));
    vi.stubGlobal("navigator", { locks: { request: lockRequest } });
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const { api } = await import("./client");
    await expect(api.getSession()).rejects.toMatchObject({ code: "SESSION_ALREADY_ACTIVE" });
    api.unloadSession();
    expect(fetch).not.toHaveBeenCalled();
    // A retry after closing the other tab must try the lock again.
    await expect(api.getSession()).rejects.toMatchObject({ code: "SESSION_ALREADY_ACTIVE" });
    expect(lockRequest).toHaveBeenCalledTimes(2);
  });

  it("releases a server-rejected tab and retries admission after the active browser closes", async () => {
    const lockRequest = vi.fn(async (name: string, _options: unknown, callback: (lock: Lock | null) => Promise<void>) => callback({ name, mode: "exclusive" }));
    vi.stubGlobal("navigator", { locks: { request: lockRequest } });
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: { code: "SESSION_ALREADY_ACTIVE", message: "Alt browser este activ." } }), { status: 429 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ history: [] })))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetch);
    const { api } = await import("./client");
    await expect(api.getSession()).rejects.toMatchObject({ code: "SESSION_ALREADY_ACTIVE" });
    api.unloadSession();
    expect(fetch).toHaveBeenCalledTimes(1);
    await expect(api.getSession()).resolves.toEqual({ history: [] });
    expect(lockRequest).toHaveBeenCalledTimes(2);
    api.unloadSession();
    expect(fetch).toHaveBeenLastCalledWith(expect.stringContaining("/api/session/unload"), expect.objectContaining({ method: "POST", keepalive: true }));
  });
});
