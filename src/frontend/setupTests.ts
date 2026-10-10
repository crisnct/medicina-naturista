import "@testing-library/jest-dom/vitest";

// Node 26 exposes its own Web Storage. Use the browser storage supplied by
// Vitest's jsdom environment so tests stay isolated and never persist to disk.
const { jsdom } = globalThis as typeof globalThis & { jsdom: { window: Window } };
Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  get: () => jsdom.window.localStorage,
});
