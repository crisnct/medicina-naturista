import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
    const lookup = vi.spyOn(api, "getHerbEvidence").mockImplementation(async (_group, condition, offset, _signal, kind) => {
      if (kind === "contraindication") return {
        ...page, evidenceKind: kind, cautionRunId: "caution-one", fragmentsCount: 1, nextOffset: null,
        fragments: [{ ...page.fragments[0], chunkId: 3, text: "Interdicție sintetică pentru Zorbita.", textHighlights: [], conditions: [{ id: 13, name: "Zorbita" }] }],
      };
      if (condition === 11) return new Promise<HerbEvidencePage>((resolve) => { finishPreviousFilter = resolve; });
      if (condition === 12) return { ...page, fragmentsCount: 0, fragments: [], nextOffset: null };
      return offset === 0 ? page : { ...page, fragments: [{ ...page.fragments[0], chunkId: 2, text: "Al doilea fragment integral.", textHighlights: [] }], nextOffset: null };
    });
    const client = new QueryClient();
    const warningId = "a".repeat(64);
    const warningText = "Precauție sintetică: <script>alert(1)</script>.";
    const safetyLookup = vi.spyOn(api, "getHerbSafety").mockImplementation(async (_group, offset) => ({
      herbId: 1, safetyRunId: "safety-one", warningsStatus: "partial", warningsCount: 2,
      warnings: [{ id: offset === 0 ? warningId : "b".repeat(64), text: offset === 0 ? warningText : "A doua atenționare sintetică.", kind: "administration", partners: [], sourcesCount: 1 }],
      nextOffset: offset === 0 ? 1 : null,
    }));
    const safetyEvidence = vi.spyOn(api, "getHerbSafetyEvidence").mockResolvedValue({
      herbId: 1, safetyRunId: "safety-one", warningId, fragmentsCount: 1, documentsCount: 1,
      fragments: [{ ...page.fragments[0], text: "Sursă pentru precauția sintetică.", textHighlights: [{ start: 0, end: 5, kind: "warning" }] }], nextOffset: null,
    });
    render(<QueryClientProvider client={client}><HerbConditionsPanel message={{
      ...message, groupId: "group-one", herbId: 1, positiveRunId: "run-one", fragmentsCount: 2, documentsCount: 1,
      cautionRunId: "caution-one", contraindicationsStatus: "partial", contraindicationsCount: 1,
      contraindications: [{ id: 13, name: "Zorbita", hasRecommendation: true }],
      contraindicationFragmentsCount: 1, contraindicationDocumentsCount: 1,
      safetyRunId: "safety-one", warningsStatus: "partial", warningsCount: 2,
      warningCandidateFragmentsCount: 1,
    }} /></QueryClientProvider>);
    const positive = within(screen.getByRole("region", { name: "Afecțiuni în care este utilă" }));
    const negative = within(screen.getByRole("region", { name: "Afecțiuni în care este interzisă" }));
    const heading = screen.getByRole("heading", { name: /utilă în 2 afecțiuni din catalog/ });
    expect(heading).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Afecțiuni asociate" })).toBeInTheDocument();
    expect(positive.getAllByRole("listitem").map((item) => item.textContent)).toEqual(["Gastrită", "Insomnie"]);
    expect(heading).not.toHaveTextContent("interzisă în");
    expect(negative.getByText(/Date parțiale/)).toBeInTheDocument();
    expect(positive.getByRole("heading", { name: "Afecțiuni în care este utilă - 2" })).toBeInTheDocument();
    expect(negative.getByRole("heading", { name: "Afecțiuni în care este interzisă - 1" })).toBeInTheDocument();
    expect(negative.queryByText(/Există și recomandări/)).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByText("(Matricaria Chamomilla)")).toBeInTheDocument();
    expect(screen.queryByText(/aceleași recomandări pozitive ca topurile/)).not.toBeInTheDocument();
    expect(lookup).not.toHaveBeenCalled();
    const safetyRegion = within(screen.getByRole("region", { name: "Atenționări și interacțiuni" }));
    expect(await safetyRegion.findByText(warningText)).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
    expect(safetyRegion.getByText(/Date parțiale/)).toBeInTheDocument();
    expect(safetyLookup).toHaveBeenCalledWith("group-one", 0, expect.any(AbortSignal));
    expect(safetyEvidence).not.toHaveBeenCalled();
    fireEvent.click(safetyRegion.getByRole("button", { name: "Încarcă mai multe" }));
    expect(await safetyRegion.findByText("A doua atenționare sintetică.")).toBeInTheDocument();
    fireEvent.click(safetyRegion.getAllByText(/Vezi sursa/)[0]);
    await waitFor(() => expect(safetyRegion.getByRole("article")).toHaveTextContent("Sursă pentru precauția sintetică."));
    expect(safetyEvidence).toHaveBeenCalledWith("group-one", warningId, 0, expect.any(AbortSignal));
    fireEvent.click(negative.getByText(/Vezi fragmente sursă/));
    expect(await negative.findByText("Interdicție sintetică pentru Zorbita.")).toBeInTheDocument();
    expect(lookup).toHaveBeenCalledWith("group-one", null, 0, expect.any(AbortSignal), "contraindication");
    fireEvent.click(positive.getByText(/Vezi fragmente sursă/));
    expect(await screen.findByText("Context integral.", { exact: false })).toBeInTheDocument();
    expect(positive.getByText("Context integral.", { exact: false })?.textContent).toBe(page.fragments[0].text);
    expect(positive.getByRole("article").querySelector(".herb-evidence-text .herb-evidence-mark-herb")).toHaveTextContent("mușețel");
    expect(positive.getByRole("article").querySelector(".herb-evidence-text .herb-evidence-mark-condition")).toHaveTextContent("Gastrită");
    expect(positive.getByText(/carte.md · liniile 2–7/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Încarcă mai multe" }));
    expect(await screen.findByText("Al doilea fragment integral.")).toBeInTheDocument();
    expect(positive.getAllByRole("article")).toHaveLength(2);
    const filter = positive.getByRole("combobox", { name: "Afecțiune" });
    fireEvent.change(filter, { target: { value: "11" } });
    await waitFor(() => expect(lookup).toHaveBeenCalledWith("group-one", 11, 0, expect.any(AbortSignal)));
    fireEvent.change(filter, { target: { value: "12" } });
    expect(await screen.findByText(/Nu există fragmente sursă/)).toBeInTheDocument();
    finishPreviousFilter(page);
    expect(positive.queryByRole("article")).not.toBeInTheDocument();
    expect(negative.getByRole("article")).toBeInTheDocument();
    lookup.mockRejectedValueOnce(new ApiError(409, "Repetați întrebarea.", "HERB_EVIDENCE_STALE"));
    fireEvent.change(filter, { target: { value: "all" } });
    fireEvent.click(positive.getByText(/Vezi fragmente sursă/));
    fireEvent.click(positive.getByText(/Vezi fragmente sursă/));
    await client.invalidateQueries({ queryKey: ["herb-evidence", "group-one", 1, "run-one", null, "positive", "caution-one"] });
    expect(await screen.findByRole("alert")).toHaveTextContent("Repetați întrebarea.");
    expect(positive.queryByRole("article")).not.toBeInTheDocument();
    expect(negative.getByRole("article")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /utilă în 2 afecțiuni/ })).toBeInTheDocument();
    client.clear();
  });

  it("distinguishes a known plant with zero associations", () => {
    render(<HerbConditionsPanel message={{ ...message, entriesCount: 0, conditions: [], contraindicationsStatus: "ready", contraindicationsCount: 0, contraindications: [] }} />);
    expect(screen.getByRole("heading", { name: /utilă în 0 afecțiuni din catalog/ })).toBeInTheDocument();
    expect(screen.getByText(/Intrarea există în catalog/)).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
    expect(screen.getByText(/Nu au fost identificate interdicții explicite/)).toBeInTheDocument();
    expect(screen.getAllByText(/Vezi fragmente sursă — 0/)).toHaveLength(2);
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
