import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { FragmentsPanel } from "./FragmentsPanel";

it("filters at 95% inclusively and excludes lower or missing scores", () => {
  render(<FragmentsPanel message={{
    kind: "fragments", role: "assistant", searchId: "search-95", fragmentsCount: 4, documentsCount: 1,
    fragments: [94.99, 95, 99, null].map((relevancePercent) => ({
      document: "plante.md", text: `Fragment ${relevancePercent}`, relevancePercent,
      semanticScore: null, lexicalScore: null, conditionMatch: null, matchLabel: "", foundByLexical: false,
    })),
  }} />);
  fireEvent.click(screen.getByText(/Am găsit 4 fragmente/));
  fireEvent.change(screen.getByLabelText("Scor minim"), { target: { value: "95" } });
  expect(screen.getByText("Fragment 95")).toBeInTheDocument();
  expect(screen.getByText("Fragment 99")).toBeInTheDocument();
  expect(screen.queryByText("Fragment 94.99")).not.toBeInTheDocument();
  expect(screen.queryByText("Fragment null")).not.toBeInTheDocument();
});
