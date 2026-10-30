import { useSyncExternalStore } from "react";
import { TEXT_PARAMETERS } from "./texts.generated";

type TextKey = keyof typeof TEXT_PARAMETERS;
type Parameters<K extends TextKey> = Record<(typeof TEXT_PARAMETERS)[K][number], string | number>;
type Arguments<K extends TextKey> = keyof Parameters<K> extends never ? [] : [parameters: Parameters<K>];

declare global {
  var __APP_TEXTS__: Record<string, string> | Record<Language, Record<string, string>> | undefined;
}

export type Language = "ro" | "en";
const preferenceKey = "naturist_language";
let language: Language = (() => {
  try {
    return localStorage.getItem(preferenceKey) === "en" ? "en" : "ro";
  } catch {
    return "ro";
  }
})();
const listeners = new Set<() => void>();
const snapshots = new Map<Language, Readonly<Record<string, string>>>();

export function getLanguage(): Language {
  return language;
}

export function locale(): string {
  return language === "en" ? "en-GB" : "ro-RO";
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function useLanguage(): Language {
  return useSyncExternalStore(subscribe, getLanguage, () => "ro" as Language);
}

export function setLanguage(next: Language): void {
  catalog(next);
  language = next;
  try {
    localStorage.setItem(preferenceKey, next);
  } catch {
    // A tab still works when storage is blocked.
  }
  applyDocumentLanguage();
  listeners.forEach((listener) => listener());
}

export function applyDocumentLanguage(): void {
  if (typeof document === "undefined") return;
  document.documentElement.lang = language;
  document.title = tr("interface.page_title");
  document.querySelector('meta[name="description"]')?.setAttribute(
    "content", tr("interface.page_description"),
  );
}

const tokens = /\{\{|\}\}|\{([a-zA-Z_][a-zA-Z_0-9]*)\}/g;

function catalog(selected: Language = language): Readonly<Record<string, string>> {
  const cached = snapshots.get(selected);
  if (cached) return cached;
  const element = typeof document === "undefined" ? null : document.getElementById("app-texts");
  const data: unknown = globalThis.__APP_TEXTS__
    ?? (element?.textContent ? JSON.parse(element.textContent) : undefined);
  if (!data || typeof data !== "object") {
    throw new Error("Missing application text bootstrap");
  }
  const bundle = data as Record<string, unknown>;
  const selectedData = bundle[selected] ?? (selected === "ro" ? bundle : undefined);
  if (!selectedData || typeof selectedData !== "object") {
    throw new Error(`Missing application catalog: ${selected}`);
  }
  const values = selectedData as Record<string, unknown>;
  for (const [key, parameters] of Object.entries(TEXT_PARAMETERS)) {
    const value = values[key];
    if (typeof value !== "string") {
      throw new Error(`Missing application text: ${key}`);
    }
    const fields = [...value.matchAll(tokens)].flatMap((match) => match[1] ? [match[1]] : []);
    if (
      /[{}]/.test(value.replace(tokens, ""))
      || fields.some((field) => !(parameters as readonly string[]).includes(field))
      || parameters.some((parameter) => !fields.includes(parameter))
    ) {
      throw new Error(`Invalid application text parameters: ${key}`);
    }
  }
  const snapshot = Object.freeze({ ...values }) as Readonly<Record<string, string>>;
  snapshots.set(selected, snapshot);
  return snapshot;
}

export function tr<K extends TextKey>(key: K, ...args: Arguments<K>): string {
  const parameters = (args[0] ?? {}) as Record<string, string | number>;
  return catalog()[key].replace(tokens, (match, name: string | undefined) => {
    if (!name) return match === "{{" ? "{" : "}";
    if (!(name in parameters)) {
      throw new Error(`Missing application text parameter: ${key}.${name}`);
    }
    return String(parameters[name]);
  });
}
