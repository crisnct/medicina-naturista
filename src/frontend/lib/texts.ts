import { TEXT_PARAMETERS } from "./texts.generated";

type TextKey = keyof typeof TEXT_PARAMETERS;
type Parameters<K extends TextKey> = Record<(typeof TEXT_PARAMETERS)[K][number], string | number>;
type Arguments<K extends TextKey> = keyof Parameters<K> extends never ? [] : [parameters: Parameters<K>];

declare global {
  var __APP_TEXTS__: Record<string, string> | undefined;
}

let snapshot: Readonly<Record<string, string>> | undefined;
const tokens = /\{\{|\}\}|\{([a-zA-Z_][a-zA-Z_0-9]*)\}/g;

function catalog(): Readonly<Record<string, string>> {
  if (snapshot) return snapshot;
  const element = typeof document === "undefined" ? null : document.getElementById("app-texts");
  const data: unknown = globalThis.__APP_TEXTS__ ?? (element?.textContent ? JSON.parse(element.textContent) : undefined);
  if (!data || typeof data !== "object") throw new Error("Missing application text bootstrap");
  const values = data as Record<string, unknown>;
  for (const [key, parameters] of Object.entries(TEXT_PARAMETERS)) {
    const value = values[key];
    if (typeof value !== "string") throw new Error(`Missing application text: ${key}`);
    const fields = [...value.matchAll(tokens)].flatMap((match) => match[1] ? [match[1]] : []);
    if (/[{}]/.test(value.replace(tokens, "")) || fields.some((field) => !(parameters as readonly string[]).includes(field)) || parameters.some((parameter) => !fields.includes(parameter))) {
      throw new Error(`Invalid application text parameters: ${key}`);
    }
  }
  snapshot = Object.freeze({ ...values }) as Readonly<Record<string, string>>;
  return snapshot;
}

export function tr<K extends TextKey>(key: K, ...args: Arguments<K>): string {
  const parameters = (args[0] ?? {}) as Record<string, string | number>;
  return catalog()[key].replace(tokens, (match, name: string | undefined) => {
    if (!name) return match === "{{" ? "{" : "}";
    if (!(name in parameters)) throw new Error(`Missing application text parameter: ${key}.${name}`);
    return String(parameters[name]);
  });
}
