import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { ALL_SIGNALS, SEARCH_SIGNALS_KEY } from "../lib/searchSignals";
import { useSearchSignals } from "./useSearchSignals";

beforeEach(() => window.localStorage.clear());

describe("useSearchSignals", () => {
  it("starts with every signal on when nothing is stored", () => {
    const { result } = renderHook(() => useSearchSignals());

    expect(result.current.signals).toEqual(ALL_SIGNALS);
  });

  it("starts from the stored choice", () => {
    window.localStorage.setItem(
      SEARCH_SIGNALS_KEY,
      JSON.stringify({ conditions: true, lexical: false, semantic: false }),
    );

    const { result } = renderHook(() => useSearchSignals());

    expect(result.current.signals).toEqual({ conditions: true, lexical: false, semantic: false });
  });

  it("starts with every signal on when the stored value is corrupt or has none on", () => {
    for (const raw of ["{", JSON.stringify({ conditions: false, lexical: false, semantic: false })]) {
      window.localStorage.setItem(SEARCH_SIGNALS_KEY, raw);

      const { result } = renderHook(() => useSearchSignals());

      expect(result.current.signals).toEqual(ALL_SIGNALS);
    }
  });

  it("keeps every change in localStorage", () => {
    const { result } = renderHook(() => useSearchSignals());

    act(() => result.current.setSignals({ conditions: false, lexical: true, semantic: true }));

    expect(result.current.signals).toEqual({ conditions: false, lexical: true, semantic: true });
    expect(JSON.parse(window.localStorage.getItem(SEARCH_SIGNALS_KEY) ?? "null")).toEqual({
      conditions: false,
      lexical: true,
      semantic: true,
    });
  });

  it("never reaches zero signals", () => {
    const { result } = renderHook(() => useSearchSignals());
    act(() => result.current.setSignals({ conditions: false, lexical: true, semantic: false }));

    act(() => result.current.setSignals({ conditions: false, lexical: false, semantic: false }));

    expect(result.current.signals).toEqual({ conditions: false, lexical: true, semantic: false });
    expect(JSON.parse(window.localStorage.getItem(SEARCH_SIGNALS_KEY) ?? "null")).toEqual({
      conditions: false,
      lexical: true,
      semantic: false,
    });
  });
});
