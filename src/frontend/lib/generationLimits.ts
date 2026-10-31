import { locale, tr } from "./texts";
import type { TokenBounds } from "../api/types";

// "26200", or digits grouped by a space, dot or comma ("26 200", "26.200"); anything else is not a count.
const GROUPED = /^\d{1,3}([ ., ]\d{3})+$/;
const PLAIN = /^[1-9][0-9]*$/;

export function parseTokens(text: string): number | null {
  const trimmed = text.trim();
  const digits = GROUPED.test(trimmed) ? trimmed.replace(/[ ., ]/g, "") : trimmed;
  if (!PLAIN.test(digits)) return null;
  const value = Number(digits);
  return Number.isSafeInteger(value) ? value : null;
}

export interface LimitsCheck {
  // The parsed values, present only when both pass.
  limits?: { batchMaxTokens: number; maxOutputTokens: number };
  // Blocking: the server would refuse these values.
  inputError?: string;
  outputError?: string;
  // Advice only.
  notes: { text: string; warning: boolean }[];
  valid: boolean;
}

// The same rules the server applies (backend/web/main.py `_check_report_limits`), so the panel
// says what is wrong before the request is made.
export function checkLimits(
  inputText: string,
  outputText: string,
  bounds: TokenBounds,
  context: number | undefined,
): LimitsCheck {
  const input = parseTokens(inputText);
  const output = parseTokens(outputText);
  const result: LimitsCheck = { notes: [], valid: false };
  if (input === null) result.inputError = tr("interface.generate_tokens_invalid");
  else if (input > bounds.max) result.inputError = tr("interface.generate_tokens_too_large", { maximum: bounds.max.toLocaleString(locale()) });
  else if (input < bounds.minInput) result.inputError = tr("interface.generate_input_too_small", { minimum: bounds.minInput.toLocaleString(locale()) });
  if (output === null) result.outputError = tr("interface.generate_tokens_invalid");
  else if (output > bounds.max) result.outputError = tr("interface.generate_tokens_too_large", { maximum: bounds.max.toLocaleString(locale()) });
  else if (context !== undefined && output >= context) result.outputError = tr("interface.generate_output_exceeds_context", { context: context.toLocaleString(locale()) });
  if (input !== null && output !== null && context !== undefined && !result.inputError && !result.outputError) {
    const room = context - output;
    if (room < bounds.minInput) {
      result.outputError = tr("interface.generate_input_no_room", { tokens: Math.max(room, 0).toLocaleString(locale()), minimum: bounds.minInput.toLocaleString(locale()) });
    } else if (room < input) {
      result.notes.push({ text: tr("interface.generate_input_effective", { tokens: room.toLocaleString(locale()), context: context.toLocaleString(locale()) }), warning: true });
    }
  }
  if (output !== null && !result.outputError && output < bounds.lowOutput) {
    result.notes.push({ text: tr("interface.generate_output_low", { threshold: bounds.lowOutput.toLocaleString(locale()) }), warning: true });
  }
  if (!result.inputError && !result.outputError && input !== null && output !== null) {
    result.limits = { batchMaxTokens: input, maxOutputTokens: output };
  }
  result.valid = result.limits !== undefined;
  return result;
}
