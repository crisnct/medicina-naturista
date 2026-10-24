import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HerbConditionsPanel } from "./HerbConditionsPanel";
import { HighlightedSource } from "./HerbEvidencePanel";
import { api, ApiError } from "../api/client";
import type { HerbConditionsMessage, HerbEvidencePage } from "../api/types";

const message: HerbConditionsMessage = {
  kind: "herb_conditions", role: "assistant", herbName: "mușețel",
  species: ["matricaria chamomilla"], entriesCount: 2,
  conditions: [{ id: 11, name: "Gastrită" }, { id: 12, name: "Insomnie" }],
};

describe("plant association results", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders the total and conditions as a list without a table", async () => {
    const page: HerbEvidencePage = {
      herbId: 1, positiveRunId: "run-one", fragmentsCount: 2, documentsCount: 1,
      fragments: [{
        chunkId: 1, document: "carte.md", lineStart: 2, lineEnd: 7,
        heading: "Gastrită", text: "🌿 mușețel: Gastrită.\nContext integral.",
        conditions: message.conditions,
        headingHighlights: [{ start: 0, end: 8, kind: "condition" }],
        textHighlights: [{ start: 2, end: 9, kind: "herb" }, { start: 11, end: 19, kind: "condition" }],
      }], nextOffset: 20,
    };
    let finishPreviousFilter: (value: HerbEvidencePage) => void = () => undefined;
    const lookup = vi.spyOn(api, "getHerbEvidence").mockImplementation(async (_group, condition, offset) => {
      if (condition === 11) return new Promise<HerbEvidencePage>((resolve) => { finishPreviousFilter = resolve; });
      if (condition === 12) return { ...page, fragmentsCount: 0, fragments: [], nextOffset: null };
      return offset === 0 ? page : { ...page, fragments: [{ ...page.fragments[0], chunkId: 2, text: "Al doilea fragment integral.", textHighlights: [] }], nextOffset: null };
    });
    const client = new QueryClient();
    render(<QueryClientProvider client={client}><HerbConditionsPanel message={{ ...message, groupId: "group-one", herbId: 1, positiveRunId: "run-one", fragmentsCount: 2, documentsCount: 1 }} /></QueryClientProvider>);
    const heading = screen.getByRole("heading", { name: /utilă în 2 afecțiuni din catalog/ });
    expect(heading).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Afecțiuni asociate" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem").map((item) => item.textContent)).toEqual(["Gastrită", "Insomnie"]);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByText("(Matricaria Chamomilla)")).toBeInTheDocument();
    expect(screen.queryByText(/aceleași recomandări pozitive ca topurile/)).not.toBeInTheDocument();
    expect(lookup).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText(/Vezi fragmentele sursă/));
    expect(await screen.findByText("Context integral.", { exact: false })).toBeInTheDocument();
    expect(document.querySelector(".herb-evidence-text")?.textContent).toBe(page.fragments[0].text);
    expect(document.querySelector(".herb-evidence-text .herb-evidence-mark-herb")).toHaveTextContent("mușețel");
    expect(document.querySelector(".herb-evidence-text .herb-evidence-mark-condition")).toHaveTextContent("Gastrită");
    expect(screen.getByText(/carte.md · liniile 2–7/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Încarcă mai multe" }));
    expect(await screen.findByText("Al doilea fragment integral.")).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(2);
    const filter = screen.getByRole("combobox", { name: "Afecțiune" });
    fireEvent.change(filter, { target: { value: "11" } });
    await waitFor(() => expect(lookup).toHaveBeenCalledWith("group-one", 11, 0, expect.any(AbortSignal)));
    fireEvent.change(filter, { target: { value: "12" } });
    expect(await screen.findByText(/Nu există fragmente sursă/)).toBeInTheDocument();
    finishPreviousFilter(page);
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
    lookup.mockRejectedValueOnce(new ApiError(409, "Repetați întrebarea.", "HERB_EVIDENCE_STALE"));
    fireEvent.change(filter, { target: { value: "all" } });
    fireEvent.click(screen.getByText(/Vezi fragmentele sursă/));
    fireEvent.click(screen.getByText(/Vezi fragmentele sursă/));
    await client.invalidateQueries({ queryKey: ["herb-evidence", "group-one", 1, "run-one", null] });
    expect(await screen.findByRole("alert")).toHaveTextContent("Repetați întrebarea.");
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /utilă în 2 afecțiuni/ })).toBeInTheDocument();
    client.clear();
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
    const source = "🌿 <script>alert(1)</script>";
    const view = render(<HighlightedSource text={source} highlights={[{ start: 2, end: Array.from(source).length, kind: "herb" }]} />);
    expect(view.container.textContent).toBe(source);
    expect(view.container.querySelector("mark")?.textContent).toBe("<script>alert(1)</script>");
    expect(view.container.querySelector("script")).toBeNull();
  });
});
