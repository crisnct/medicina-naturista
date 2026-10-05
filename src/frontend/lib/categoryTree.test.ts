import { describe, expect, it } from "vitest";
import type { CategoryNode } from "../api/types";
import { collectRealIds, nodeCheckState, selectedDocumentCount, toggleNode } from "./categoryTree";

// Mirrors the tree tests/unit/web/test_web.py builds for the same scenario
// (test_report_started_message_counts_only_selected_categories).
const tree: CategoryNode = {
  id: "",
  label: "(fără categorie)",
  ownDocuments: 0,
  totalDocuments: 15,
  isReal: false,
  children: [
    { id: "Cancer", label: "Cancer", ownDocuments: 4, totalDocuments: 4, isReal: true, children: [] },
    {
      id: "Centrul",
      label: "Centrul",
      ownDocuments: 0,
      totalDocuments: 11,
      isReal: false,
      children: [
        {
          id: "Centrul/Anatomie",
          label: "Anatomie",
          ownDocuments: 11,
          totalDocuments: 11,
          isReal: true,
          children: [],
        },
      ],
    },
  ],
};

describe("collectRealIds", () => {
  it("only lists ids with documents of their own, never structural-only branches", () => {
    expect(collectRealIds(tree).sort()).toEqual(["Cancer", "Centrul/Anatomie"]);
  });
});

describe("nodeCheckState", () => {
  it("is unchecked when nothing under the node is selected", () => {
    expect(nodeCheckState(tree, new Set())).toBe("unchecked");
  });

  it("is checked once every real descendant is selected", () => {
    expect(nodeCheckState(tree, new Set(["Cancer", "Centrul/Anatomie"]))).toBe("checked");
  });

  it("is mixed when only some real descendants are selected", () => {
    const centrul = tree.children[1];
    expect(nodeCheckState(tree, new Set(["Cancer"]))).toBe("mixed");
    expect(nodeCheckState(centrul, new Set(["Cancer"]))).toBe("unchecked");
  });
});

describe("toggleNode", () => {
  it("cascades checking a structural branch to every real descendant, not itself", () => {
    const centrul = tree.children[1];
    const next = toggleNode(centrul, new Set(), true);
    expect(next).toEqual(new Set(["Centrul/Anatomie"]));
  });

  it("cascades unchecking without touching ids outside the node", () => {
    const centrul = tree.children[1];
    const next = toggleNode(centrul, new Set(["Cancer", "Centrul/Anatomie"]), false);
    expect(next).toEqual(new Set(["Cancer"]));
  });
});

describe("selectedDocumentCount", () => {
  it("sums ownDocuments, never totalDocuments (which would double-count a folder and its subfolder)", () => {
    expect(selectedDocumentCount(tree, new Set(["Cancer"]))).toBe(4);
    expect(selectedDocumentCount(tree, new Set(["Cancer", "Centrul/Anatomie"]))).toBe(15);
    expect(selectedDocumentCount(tree, new Set(["unknown-id"]))).toBe(0);
  });
});
