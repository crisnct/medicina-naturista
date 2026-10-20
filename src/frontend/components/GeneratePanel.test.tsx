import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FragmentItem, GenerateMessage } from "../api/types";
import { GeneratePanel } from "./GeneratePanel";
import { api } from "../api/client";

beforeEach(() => {
  vi.spyOn(api, "getReportDurationEstimate").mockImplementation(() => new Promise(() => {}));
});
afterEach(() => vi.restoreAllMocks());

const message: GenerateMessage = { kind: "generate", role: "assistant", searchId: "search-1", busy: false };

function fragment(relevancePercent: number | null): FragmentItem {
  return {
    document: "a.md",
    text: "Text.",
    relevancePercent,
    semanticScore: null,
    lexicalScore: null,
    conditionMatch: null,
    matchLabel: "",
    foundByLexical: false,
  };
}

function renderPanel(fragments?: FragmentItem[], onGenerate = vi.fn()) {
  render(<GeneratePanel message={message} fragments={fragments} onGenerate={onGenerate}
    reportModels={["ollama-gemma4:12b"]} allowedReportModels={["ollama-gemma4:12b"]} />);
  return onGenerate;
}

const button = () => screen.getByRole("button", { name: /Generează raportul/ });
const chooseMinScore = (value: number) =>
  fireEvent.change(screen.getByLabelText("Scor minim"), { target: { value: String(value) } });

describe("the minimum score next to Generează rețeta", () => {
  it("sends every fragment by default", () => {
    const onGenerate = renderPanel([fragment(10)]);

    fireEvent.click(button());

    expect(onGenerate).toHaveBeenCalledWith("search-1", 0, "ollama-gemma4:12b");
  });

  it("sends the chosen threshold, which includes a fragment exactly at it", () => {
    const onGenerate = renderPanel([fragment(30), fragment(50)]);

    chooseMinScore(50);
    expect(button()).toBeEnabled();
    fireEvent.click(button());

    expect(onGenerate).toHaveBeenCalledWith("search-1", 50, "ollama-gemma4:12b");
  });

  it("disables the button when no fragment reaches the threshold", () => {
    renderPanel([fragment(30), fragment(null)]);

    chooseMinScore(50);

    expect(button()).toBeDisabled();
    expect(screen.getByText("Niciun fragment nu atinge scorul minim selectat.")).toBeInTheDocument();
  });

  it("leaves the check to the server when the search's fragments are not in the chat", () => {
    renderPanel(undefined);

    chooseMinScore(90);

    expect(button()).toBeEnabled();
  });

  it("accepts exactly 95% and sends that threshold to recipe generation", () => {
    const onGenerate = renderPanel([fragment(94.99), fragment(95)]);
    chooseMinScore(95);
    expect(button()).toBeEnabled();
    fireEvent.click(button());
    expect(onGenerate).toHaveBeenCalledWith("search-1", 95, "ollama-gemma4:12b");
  });

  it("disables generation at 95% when all scores are lower", () => {
    renderPanel([fragment(94.99), fragment(null)]);
    chooseMinScore(95);
    expect(button()).toBeDisabled();
  });
});
