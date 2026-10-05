import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CategoryNode, FragmentsMessage, SearchSignals } from "../api/types";
import { ALL_SIGNALS } from "../lib/searchSignals";
import { CategoryFilterPanel, LAST_SIGNAL_HINT } from "./CategoryFilterPanel";
import { FragmentsPanel } from "./FragmentsPanel";

const tree: CategoryNode = {
  id: "",
  label: "(fără categorie)",
  ownDocuments: 0,
  totalDocuments: 2,
  isReal: false,
  children: [{ id: "Cancer", label: "Cancer", ownDocuments: 2, totalDocuments: 2, isReal: true, children: [] }],
};

function renderPanel(signals: SearchSignals, onSignalsChange = vi.fn()) {
  render(
    <CategoryFilterPanel
      tree={tree}
      selected={new Set(["Cancer"])}
      onChange={vi.fn()}
      signals={signals}
      onSignalsChange={onSignalsChange}
    />,
  );
  return onSignalsChange;
}

describe("the search type checkboxes", () => {
  it("offers the three search types, all checked by default", () => {
    renderPanel(ALL_SIGNALS);

    for (const label of ["Căutare afecțiuni", "Căutare lexicală", "Căutare semantică"]) {
      const checkbox = screen.getByLabelText(label);
      expect(checkbox).toBeChecked();
      expect(checkbox).toBeEnabled();
    }
  });

  it("reports the new choice when a box is unchecked", () => {
    const onSignalsChange = renderPanel(ALL_SIGNALS);

    fireEvent.click(screen.getByLabelText("Căutare lexicală"));

    expect(onSignalsChange).toHaveBeenCalledWith({ conditions: true, lexical: false, semantic: true });
  });

  it("disables the last checked box, so the choice cannot reach zero", () => {
    renderPanel({ conditions: false, lexical: true, semantic: false });

    const last = screen.getByLabelText("Căutare lexicală");
    expect(last).toBeChecked();
    expect(last).toBeDisabled();
    expect(last.closest("label")).toHaveAttribute("title", LAST_SIGNAL_HINT);
    // The unchecked ones stay available.
    expect(screen.getByLabelText("Căutare afecțiuni")).toBeEnabled();
    expect(screen.getByLabelText("Căutare semantică")).toBeEnabled();
  });

  it("does not disable a checked box while another one is checked too", () => {
    renderPanel({ conditions: true, lexical: false, semantic: true });

    expect(screen.getByLabelText("Căutare afecțiuni")).toBeEnabled();
    expect(screen.getByLabelText("Căutare semantică")).toBeEnabled();
  });
});

const fragments: FragmentsMessage = {
  kind: "fragments",
  role: "assistant",
  searchId: "s1",
  fragmentsCount: 1,
  documentsCount: 1,
  fragments: [
    {
      document: "Afectiuni/Guta.md",
      text: "Textul fragmentului.",
      relevancePercent: 80,
      semanticScore: 0.5,
      lexicalScore: 1,
      conditionMatch: "title",
      matchLabel: "Găsire Lexicală",
      foundByLexical: true,
    },
  ],
};

function filterLabels(): string[] {
  return ["Scor minim", "Scor semantic", "Afecțiune", "Găsire lexicală", "Document"].filter(
    (label) => screen.queryByText(label, { selector: "label" }) !== null,
  );
}

describe("the fragments panel", () => {
  it("shows every score component and filter for a search scored with every signal", () => {
    render(<FragmentsPanel message={{ ...fragments, signals: ALL_SIGNALS }} />);

    expect(filterLabels()).toEqual(["Scor minim", "Scor semantic", "Afecțiune", "Găsire lexicală", "Document"]);
    const line = screen.getByText(/Scor relevanță: 80%/);
    expect(line).toHaveTextContent("Scor semantic: 0.50");
    expect(line).toHaveTextContent("Scor lexical: 1.00");
    expect(line).toHaveTextContent("Afecțiune în titlu");
    expect(line).toHaveTextContent("Găsire Lexicală");
  });

  it("treats a message without signals as scored with every signal", () => {
    render(<FragmentsPanel message={fragments} />);

    expect(filterLabels()).toEqual(["Scor minim", "Scor semantic", "Afecțiune", "Găsire lexicală", "Document"]);
  });

  it("hides what the semantic signal brings when it was off", () => {
    render(<FragmentsPanel message={{ ...fragments, signals: { conditions: true, lexical: true, semantic: false } }} />);

    expect(filterLabels()).toEqual(["Scor minim", "Afecțiune", "Găsire lexicală", "Document"]);
    expect(screen.getByText(/Scor relevanță: 80%/)).not.toHaveTextContent("Scor semantic");
  });

  it("hides what the lexical signal brings when it was off", () => {
    render(<FragmentsPanel message={{ ...fragments, signals: { conditions: true, lexical: false, semantic: true } }} />);

    expect(filterLabels()).toEqual(["Scor minim", "Scor semantic", "Afecțiune", "Document"]);
    const line = screen.getByText(/Scor relevanță: 80%/);
    expect(line).not.toHaveTextContent("Scor lexical");
    expect(line).not.toHaveTextContent("Găsire Lexicală");
  });

  it("hides what the conditions signal brings when it was off", () => {
    render(<FragmentsPanel message={{ ...fragments, signals: { conditions: false, lexical: true, semantic: true } }} />);

    expect(filterLabels()).toEqual(["Scor minim", "Scor semantic", "Găsire lexicală", "Document"]);
    expect(screen.getByText(/Scor relevanță: 80%/)).not.toHaveTextContent("Afecțiune în titlu");
  });

  it("always keeps the relevance score and the document filter", () => {
    render(<FragmentsPanel message={{ ...fragments, signals: { conditions: false, lexical: false, semantic: true } }} />);

    expect(filterLabels()).toEqual(["Scor minim", "Scor semantic", "Document"]);
    expect(screen.getByText(/Scor relevanță: 80%/)).toBeInTheDocument();
  });
});
