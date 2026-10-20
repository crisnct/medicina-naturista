import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HerbConditionsPanel } from "./HerbConditionsPanel";
import type { HerbConditionsMessage } from "../api/types";

const message: HerbConditionsMessage = {
  kind: "herb_conditions", role: "assistant", herbName: "mușețel",
  species: ["matricaria chamomilla"], entriesCount: 2,
  conditions: [{ id: 11, name: "Gastrită" }, { id: 12, name: "Insomnie" }],
};

describe("plant association results", () => {
  it("renders the total and conditions as a list without a table", () => {
    render(<HerbConditionsPanel message={message} />);
    const heading = screen.getByRole("heading", { name: /utilă în 2 afecțiuni din catalog/ });
    expect(heading).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Afecțiuni asociate" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem").map((item) => item.textContent)).toEqual(["Gastrită", "Insomnie"]);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByText("(Matricaria Chamomilla)")).toBeInTheDocument();
  });

  it("distinguishes a known plant with zero associations", () => {
    render(<HerbConditionsPanel message={{ ...message, entriesCount: 0, conditions: [] }} />);
    expect(screen.getByRole("heading", { name: /utilă în 0 afecțiuni din catalog/ })).toBeInTheDocument();
    expect(screen.getByText(/Intrarea există în catalog/)).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("renders names as text rather than executable HTML", () => {
    render(<HerbConditionsPanel message={{ ...message, conditions: [{ id: 1, name: "<script>alert(1)</script>" }] }} />);
    expect(screen.getByText("<script>alert(1)</script>")).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
  });
});
