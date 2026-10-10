import { describe, expect, it } from "vitest";
import { reconcileRetention } from "./retention";
import type { ChatMessage } from "../api/types";

const messages: ChatMessage[] = [
  { kind: "text", role: "user", content: "old", groupId: "old" },
  { kind: "generate", role: "assistant", searchId: "s1", busy: false, groupId: "old" },
  { kind: "download", role: "assistant", reportId: "r1", url: "/r1", filename: "r1.pdf", groupId: "old" },
  { kind: "text", role: "user", content: "new", groupId: "new" },
];

describe("retention", () => {
  it("removes a whole evicted interaction and all its actions", () => {
    expect(reconcileRetention(messages, { evictedGroupIds: ["old"] })).toEqual([messages[3]]);
  });
  it("removes invalidated search/report actions without losing unrelated messages", () => {
    expect(reconcileRetention(messages, { evictedSearchIds: ["s1"], evictedReportIds: ["r1"] })).toEqual([messages[0], messages[3]]);
  });
  it("preserves history when the server has no invalidations", () => {
    expect(reconcileRetention(messages, {})).toEqual(messages);
  });
});
