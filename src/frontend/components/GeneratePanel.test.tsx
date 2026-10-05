import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { FragmentItem, GenerateMessage } from "../api/types";
import { GeneratePanel } from "./GeneratePanel";

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
  render(<GeneratePanel message={message} fragments={fragments} onGenerate={onGenerate} />);
  return onGenerate;
}

const button = () => screen.getByRole("button", { name: /Generează rețeta/ });
const chooseMinScore = (value: number) =>
  fireEvent.change(screen.getByLabelText("Scor minim"), { target: { value: String(value) } });

describe("the minimum score next to Generează rețeta", () => {
  it("sends every fragment by default", () => {
    const onGenerate = renderPanel([fragment(10)]);

    fireEvent.click(button());

    expect(onGenerate).toHaveBeenCalledWith("search-1", 0);
  });

  it("sends the chosen threshold, which includes a fragment exactly at it", () => {
    const onGenerate = renderPanel([fragment(30), fragment(50)]);

    chooseMinScore(50);
    expect(button()).toBeEnabled();
    fireEvent.click(button());

    expect(onGenerate).toHaveBeenCalledWith("search-1", 50);
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
});
