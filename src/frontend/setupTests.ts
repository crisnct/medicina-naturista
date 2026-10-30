import "@testing-library/jest-dom/vitest";
declare const __APP_TEST_TEXTS__: Record<"ro" | "en", Record<string, string>>;
globalThis.__APP_TEXTS__ = __APP_TEST_TEXTS__;

// Node 26 exposes its own Web Storage. Use the browser storage supplied by
// Vitest's jsdom environment so tests stay isolated and never persist to disk.
const { jsdom } = globalThis as typeof globalThis & { jsdom: { window: Window } };
Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  get: () => jsdom.window.localStorage,
});
