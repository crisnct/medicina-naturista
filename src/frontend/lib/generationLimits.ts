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
  // The parsed values, present only when all pass.
  limits?: { batchMaxTokens: number; maxOutputTokens: number; thinkingTokens?: number };
  // Blocking: the server would refuse these values.
  inputError?: string;
  outputError?: string;
  thinkingError?: string;
  // Advice only.
  notes: { text: string; warning: boolean }[];
  valid: boolean;
}

// The same rules the server applies (backend/web/main.py `_check_report_limits`), so the panel
// says what is wrong before the request is made. `thinkingText` is undefined while the chosen
// effort leaves the model without thinking; the thinking then takes no room.
export function checkLimits(
  inputText: string,
  outputText: string,
  bounds: TokenBounds,
  context: number | undefined,
  thinkingText?: string,
): LimitsCheck {
  const input = parseTokens(inputText);
  const output = parseTokens(outputText);
  const thinking = thinkingText === undefined ? undefined : parseTokens(thinkingText);
  const result: LimitsCheck = { notes: [], valid: false };
  if (thinking === null) result.thinkingError = tr("interface.generate_tokens_invalid");
  else if (thinking !== undefined && thinking > bounds.max) result.thinkingError = tr("interface.generate_tokens_too_large", { maximum: bounds.max.toLocaleString(locale()) });
  else if (thinking !== undefined && context !== undefined && thinking > Math.floor(context / bounds.thinkingContextDivisor)) {
    result.thinkingError = tr("interface.generate_thinking_too_large", { limit: Math.floor(context / bounds.thinkingContextDivisor).toLocaleString(locale()) });
  }
  if (input === null) result.inputError = tr("interface.generate_tokens_invalid");
  else if (input > bounds.max) result.inputError = tr("interface.generate_tokens_too_large", { maximum: bounds.max.toLocaleString(locale()) });
  else if (input < bounds.minInput) result.inputError = tr("interface.generate_input_too_small", { minimum: bounds.minInput.toLocaleString(locale()) });
  if (output === null) result.outputError = tr("interface.generate_tokens_invalid");
  else if (output > bounds.max) result.outputError = tr("interface.generate_tokens_too_large", { maximum: bounds.max.toLocaleString(locale()) });
  else if (context !== undefined && output >= context) result.outputError = tr("interface.generate_output_exceeds_context", { context: context.toLocaleString(locale()) });
  if (input !== null && output !== null && context !== undefined && !result.inputError && !result.outputError && !result.thinkingError) {
    const room = context - output - (thinking ?? 0);
    if (room < bounds.minInput) {
      result.outputError = tr("interface.generate_input_no_room", { tokens: Math.max(room, 0).toLocaleString(locale()), minimum: bounds.minInput.toLocaleString(locale()) });
    } else if (room < input) {
      result.notes.push({ text: tr("interface.generate_input_effective", { tokens: room.toLocaleString(locale()), context: context.toLocaleString(locale()) }), warning: true });
    }
  }
  if (output !== null && !result.outputError && output < bounds.lowOutput) {
    result.notes.push({ text: tr("interface.generate_output_low", { threshold: bounds.lowOutput.toLocaleString(locale()) }), warning: true });
  }
  if (!result.inputError && !result.outputError && !result.thinkingError && input !== null && output !== null && thinking !== null) {
    result.limits = { batchMaxTokens: input, maxOutputTokens: output, ...(thinking === undefined ? {} : { thinkingTokens: thinking }) };
  }
  result.valid = result.limits !== undefined;
  return result;
}
