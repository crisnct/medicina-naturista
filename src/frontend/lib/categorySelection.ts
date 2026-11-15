import type { Language } from "./texts";

// localStorage key of the sources the patient ticked, one list per language (the folders
// of the Romanian and English corpora differ). Per browser, not synced between devices.
export const CATEGORY_SELECTION_KEY = "naturist.categorySelection";

function readAll(): Partial<Record<Language, unknown>> {
  try {
    const raw = window.localStorage.getItem(CATEGORY_SELECTION_KEY);
    const parsed: unknown = raw === null ? null : JSON.parse(raw);
    return typeof parsed === "object" && parsed !== null ? parsed : {};
  } catch {
    return {};
  }
}

// The remembered selection of a language, or null when there is none (or it is
// unreadable): an empty list is a real choice, "nothing ticked".
export function readStoredSelection(language: Language): Set<string> | null {
  const stored = readAll()[language];
  if (!Array.isArray(stored) || stored.some((id) => typeof id !== "string")) return null;
  return new Set(stored as string[]);
}

export function storeSelection(language: Language, selected: Set<string>): void {
  try {
    const all = { ...readAll(), [language]: [...selected] };
    window.localStorage.setItem(CATEGORY_SELECTION_KEY, JSON.stringify(all));
  } catch {
    // Private window or blocked storage: the choice just is not remembered.
  }
}
