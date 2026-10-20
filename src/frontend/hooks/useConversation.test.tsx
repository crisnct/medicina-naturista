import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../api/client";
import { useConversation } from "./useConversation";
import type { ChatMessage, ReportGeneration } from "../api/types";

const signals = { conditions: true, lexical: true, semantic: true };
const old: ChatMessage[] = [
  { kind: "text", role: "user", content: "old", groupId: "old" },
  { kind: "generate", role: "assistant", searchId: "s", busy: false, groupId: "old" },
];

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  return renderHook(() => useConversation(), { wrapper });
}

afterEach(() => vi.restoreAllMocks());
beforeEach(() => vi.spyOn(api, "getReportModels").mockResolvedValue({
  models: ["ollama-gemma4:12b"],
  defaultModel: "ollama-gemma4:12b",
  allowedModels: ["ollama-gemma4:12b"],
}));

describe("conversation resource reconciliation", () => {
  it("shows server queue position, keeps the panel busy and can cancel without resubmission", async () => {
    const queued: ReportGeneration = {
      jobId: "queued-job", searchId: "s", state: "accepted", stage: "queued",
      provider: "synthetic", model: "synthetic", createdAt: 1, deadlineAt: 100,
      queuePosition: 2, workerActive: true,
    };
    const cancelled: ReportGeneration = {
      ...queued, state: "cancelled", workerActive: false, queuePosition: null,
      message: "Generarea a fost anulată.",
    };
    const getSession = vi.spyOn(api, "getSession").mockResolvedValue({ history: old });
    const generate = vi.spyOn(api, "generateReport").mockResolvedValue(queued);
    vi.spyOn(api, "getGeneration").mockResolvedValue(queued);
    const cancel = vi.spyOn(api, "cancelGeneration").mockResolvedValue(cancelled);
    const { result } = mount();
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => result.current.generateReport("s", 0));
    await waitFor(() => expect(result.current.generationFeedback.s?.progress).toContain("Poziția: 2"));
    expect(result.current.history[1]).toMatchObject({ kind: "generate", busy: true });
    expect(result.current.isGenerating).toBe(true);
    getSession.mockResolvedValue({ history: old, generations: [cancelled] });
    act(() => result.current.generationFeedback.s?.cancel?.());
    await waitFor(() => expect(result.current.generationFeedback.s?.message).toBe(cancelled.message));
    expect(cancel).toHaveBeenCalledWith("queued-job", expect.anything());
    expect(generate).toHaveBeenCalledTimes(1);
    expect(result.current.history[1]).toMatchObject({ kind: "generate", busy: false });
  });

  it("classifies before searching and skips condition identification for diverse", async () => {
    vi.spyOn(api, "getSession").mockResolvedValue({ history: [] });
    vi.spyOn(api, "sendMessage").mockResolvedValue({ messages: [], startSearch: false, classifyMessage: true, contextRevision: 8 });
    const classification = vi.spyOn(api, "classifyMessage").mockResolvedValue({ messages: [], intent: "diverse", startSearch: true, identifyCondition: false, contextRevision: 8 });
    const condition = vi.spyOn(api, "identifyCondition");
    const search = vi.spyOn(api, "search").mockResolvedValue({ messages: [] });
    const { result } = mount();
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => result.current.sendMessage("cum prepar o infuzie?", [], signals));
    await waitFor(() => expect(result.current.isSending).toBe(false));
    expect(classification).toHaveBeenCalledWith(8);
    expect(search).toHaveBeenCalledWith(8);
    expect(condition).not.toHaveBeenCalled();
    expect(classification.mock.invocationCallOrder[0]).toBeLessThan(search.mock.invocationCallOrder[0]);
  });

  it("shows plant results without starting a fragment search", async () => {
    vi.spyOn(api, "getSession").mockResolvedValue({ history: [] });
    vi.spyOn(api, "sendMessage").mockResolvedValue({ messages: [], startSearch: false, classifyMessage: true, contextRevision: 9 });
    const message: ChatMessage = { kind: "herb_conditions", role: "assistant", herbName: "musetel", species: [], entriesCount: 0, conditions: [] };
    vi.spyOn(api, "classifyMessage").mockResolvedValue({ messages: [message], intent: "planta", startSearch: false, contextRevision: 9 });
    const search = vi.spyOn(api, "search");
    const condition = vi.spyOn(api, "identifyCondition");
    const { result } = mount();
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => result.current.sendMessage("musetel", [], signals));
    await waitFor(() => expect(result.current.history).toEqual([message]));
    expect(search).not.toHaveBeenCalled();
    expect(condition).not.toHaveBeenCalled();
  });

  it("does not retrieve when classification is cancelled", async () => {
    vi.spyOn(api, "getSession").mockResolvedValue({ history: [] });
    vi.spyOn(api, "sendMessage").mockResolvedValue({ messages: [], startSearch: false, classifyMessage: true, contextRevision: 10 });
    vi.spyOn(api, "classifyMessage").mockResolvedValue({ messages: [], startSearch: true, cancelled: true });
    const search = vi.spyOn(api, "search");
    const { result } = mount();
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => result.current.sendMessage("old", [], signals));
    await waitFor(() => expect(result.current.isSending).toBe(false));
    expect(search).not.toHaveBeenCalled();
    expect(result.current.isClassifying).toBe(false);
  });

  it("removes an entire evicted group and passes the message revision to retrieval", async () => {
    vi.spyOn(api, "getSession").mockResolvedValue({ history: old });
    vi.spyOn(api, "sendMessage").mockResolvedValue({
      messages: [{ kind: "text", role: "user", content: "new", groupId: "new" }],
      startSearch: true, contextRevision: 4, evictedGroupIds: ["old"], evictedSearchIds: ["s"],
    });
    const search = vi.spyOn(api, "search").mockResolvedValue({ messages: [], cancelled: true });
    const { result } = mount();
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => result.current.sendMessage("new", [], signals));
    await waitFor(() => expect(search).toHaveBeenCalledWith(4));
    await waitFor(() => expect(result.current.isSending).toBe(false));
    expect(result.current.history).toEqual([{ kind: "text", role: "user", content: "new", groupId: "new" }]);
  });

  it("shows a controlled capacity error without retrying an AI operation", async () => {
    vi.spyOn(api, "getSession").mockResolvedValue({ history: old });
    const generate = vi.spyOn(api, "generateReport").mockRejectedValue(new ApiError(409, "Buget insuficient.", "SESSION_BUDGET"));
    const { result } = mount();
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => result.current.generateReport("s", 0));
    await waitFor(() => expect(result.current.generationFeedback.s?.message).toBe("Buget insuficient."));
    expect(generate).toHaveBeenCalledTimes(1);
    expect(result.current.history[1]).toMatchObject({ kind: "generate", busy: false });
  });
  it("does not retry a stale selection or run a global search", async () => {
    vi.spyOn(api, "getSession").mockResolvedValue({ history: old });
    vi.spyOn(api, "sendMessage").mockResolvedValue({ messages: [], startSearch: true });
    const search = vi.spyOn(api, "search").mockRejectedValue(new ApiError(409, "Selectați din nou sursele.", "CATEGORY_SELECTION_STALE"));
    const { result } = mount();
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => result.current.sendMessage("new", ["removed"], signals));
    await waitFor(() => expect(result.current.banner).toContain("Selectați din nou sursele."));
    expect(search).toHaveBeenCalledTimes(1);
    expect(api.sendMessage).toHaveBeenCalledTimes(1);
  });

});
