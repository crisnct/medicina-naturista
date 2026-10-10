import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../api/client";
import { useConversation } from "./useConversation";
import type { ChatMessage } from "../api/types";

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

describe("conversation resource reconciliation", () => {
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
    await waitFor(() => expect(result.current.banner).toBe("Buget insuficient."));
    expect(generate).toHaveBeenCalledTimes(1);
    expect(result.current.history[1]).toMatchObject({ kind: "generate", busy: false });
  });
});
