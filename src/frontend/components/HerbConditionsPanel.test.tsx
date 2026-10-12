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
  it("renders the total above the conditions without an ID column", () => {
    render(<HerbConditionsPanel message={message} />);
    const heading = screen.getByRole("heading", { name: /utilă în 2 afecțiuni/ });
    expect(heading).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(3);
    expect(screen.getAllByRole("columnheader")).toHaveLength(1);
    expect(screen.queryByRole("cell", { name: "11" })).not.toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Gastrită" })).toBeInTheDocument();
    expect(screen.getByText("matricaria chamomilla")).toBeInTheDocument();
  });

  it("distinguishes a known plant with zero associations", () => {
    render(<HerbConditionsPanel message={{ ...message, entriesCount: 0, conditions: [] }} />);
    expect(screen.getByRole("heading", { name: /utilă în 0 afecțiuni/ })).toBeInTheDocument();
    expect(screen.getByText(/Planta există în catalog/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("renders names as text rather than executable HTML", () => {
    render(<HerbConditionsPanel message={{ ...message, conditions: [{ id: 1, name: "<script>alert(1)</script>" }] }} />);
    expect(screen.getByText("<script>alert(1)</script>")).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
  });
});
