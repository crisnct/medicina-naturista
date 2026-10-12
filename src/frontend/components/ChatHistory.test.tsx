import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChatMessage } from "../api/types";
import { ChatHistory } from "./ChatHistory";

const history: ChatMessage[] = [{ kind: "text", role: "user", content: "Salut" }];

afterEach(() => vi.restoreAllMocks());

describe("conversation scrolling", () => {
  it("does not scroll when messages or the pending indicator change", () => {
    const pageScroll = vi.spyOn(window, "scrollTo");
    const scrollIntoView = vi.fn();
    const scrollTop = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: scrollIntoView });
    const { rerender } = render(<ChatHistory history={history} pending={false} onGenerate={vi.fn()} />);
    const log = screen.getByRole("log");
    Object.defineProperties(log, {
      scrollHeight: { value: 1200 },
      scrollTop: { configurable: true, get: () => 0, set: scrollTop },
    });

    const nextHistory: ChatMessage[] = [...history, { kind: "text", role: "assistant", content: "Bună" }];
    rerender(<ChatHistory history={nextHistory} pending={true} onGenerate={vi.fn()} />);
    rerender(<ChatHistory history={nextHistory} pending={false} onGenerate={vi.fn()} />);

    expect(screen.getByText("Bună")).toBeInTheDocument();
    expect(scrollTop).not.toHaveBeenCalled();
    expect(scrollIntoView).not.toHaveBeenCalled();
    expect(pageScroll).not.toHaveBeenCalled();
  });
});
