import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { useCategories } from "./useCategories";

afterEach(() => vi.restoreAllMocks());

it("keeps an empty selection after a generation removes the chosen category", async () => {
  vi.spyOn(api, "getCategories").mockResolvedValue({ tree: null, defaultSelection: ["A", "B"], indexGeneration: "first" });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const { result } = renderHook(() => useCategories(), { wrapper });
  await waitFor(() => expect([...result.current.selected]).toEqual(["A", "B"]));
  act(() => result.current.setSelected(new Set(["A"])));
  act(() => client.setQueryData(["categories", "ro"], { tree: null, defaultSelection: ["B", "C"], indexGeneration: "second" }));
  await waitFor(() => expect(result.current.selected.size).toBe(0));
});
