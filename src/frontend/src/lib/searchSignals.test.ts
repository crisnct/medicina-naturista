import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ALL_SIGNALS, SEARCH_SIGNALS_KEY, countOn, readStoredSignals, storeSignals } from "./searchSignals";

beforeEach(() => window.localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("readStoredSignals", () => {
  it("returns every signal when nothing is stored", () => {
    expect(readStoredSignals()).toEqual(ALL_SIGNALS);
  });

  it("returns the stored choice", () => {
    window.localStorage.setItem(
      SEARCH_SIGNALS_KEY,
      JSON.stringify({ conditions: false, lexical: true, semantic: true }),
    );

    expect(readStoredSignals()).toEqual({ conditions: false, lexical: true, semantic: true });
  });

  it("falls back to every signal for corrupt or malformed values", () => {
    for (const raw of ["not json", "null", "42", "[]", "{}", '{"conditions":true}', '{"conditions":1,"lexical":1,"semantic":1}']) {
      window.localStorage.setItem(SEARCH_SIGNALS_KEY, raw);

      expect(readStoredSignals(), raw).toEqual(ALL_SIGNALS);
    }
  });

  it("falls back to every signal when the stored choice has none on", () => {
    window.localStorage.setItem(
      SEARCH_SIGNALS_KEY,
      JSON.stringify({ conditions: false, lexical: false, semantic: false }),
    );

    expect(readStoredSignals()).toEqual(ALL_SIGNALS);
  });

  it("falls back to every signal when the storage cannot be read", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });

    expect(readStoredSignals()).toEqual(ALL_SIGNALS);
  });
});

describe("storeSignals", () => {
  it("writes the choice under the documented key", () => {
    storeSignals({ conditions: true, lexical: false, semantic: true });

    expect(JSON.parse(window.localStorage.getItem("naturist.searchSignals") ?? "null")).toEqual({
      conditions: true,
      lexical: false,
      semantic: true,
    });
  });

  it("does not throw when the storage cannot be written", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });

    expect(() => storeSignals(ALL_SIGNALS)).not.toThrow();
  });
});

describe("countOn", () => {
  it("counts the signals that are on", () => {
    expect(countOn(ALL_SIGNALS)).toBe(3);
    expect(countOn({ conditions: false, lexical: true, semantic: false })).toBe(1);
  });
});
