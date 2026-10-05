import type { SearchSignals } from "../api/types";

// Which signals make up the score of a search, chosen in the "Căutare avansată"
// panel: conditions (A), lexical (B), semantic (C). Mirrors ai/search.py's
// SearchSignals; the server validates the choice too.
export const ALL_SIGNALS: SearchSignals = { conditions: true, lexical: true, semantic: true };

// localStorage key of the last choice (per browser, not synced between devices).
export const SEARCH_SIGNALS_KEY = "naturist.searchSignals";

export const SIGNAL_KEYS = ["conditions", "lexical", "semantic"] as const;

export function countOn(signals: SearchSignals): number {
  return SIGNAL_KEYS.filter((key) => signals[key]).length;
}

// The stored choice, or every signal on when it is missing, unreadable,
// malformed or has no signal on (the UI never lets zero be chosen).
export function readStoredSignals(): SearchSignals {
  try {
    const raw = window.localStorage.getItem(SEARCH_SIGNALS_KEY);
    if (raw === null) return ALL_SIGNALS;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return ALL_SIGNALS;
    const record = parsed as Record<string, unknown>;
    if (SIGNAL_KEYS.some((key) => typeof record[key] !== "boolean")) return ALL_SIGNALS;
    const signals: SearchSignals = {
      conditions: record.conditions as boolean,
      lexical: record.lexical as boolean,
      semantic: record.semantic as boolean,
    };
    return countOn(signals) === 0 ? ALL_SIGNALS : signals;
  } catch {
    return ALL_SIGNALS;
  }
}

export function storeSignals(signals: SearchSignals): void {
  try {
    window.localStorage.setItem(SEARCH_SIGNALS_KEY, JSON.stringify(signals));
  } catch {
    // Private window or blocked storage: the choice just is not remembered.
  }
}
