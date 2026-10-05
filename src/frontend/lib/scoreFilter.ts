import type { FragmentItem } from "../api/types";

// "Scor minim" thresholds (relevance percent), shared by the fragments panel
// filter and the one next to "Generează rețeta"; 0 means no restriction.
export const MIN_SCORE_OPTIONS: { value: number; label: string }[] = [
  { value: 0, label: "Toate" },
  { value: 25, label: "≥ 25%" },
  { value: 50, label: "≥ 50%" },
  { value: 75, label: "≥ 75%" },
  { value: 90, label: "≥ 90%" },
];

// True when the fragment's relevance reaches the threshold (inclusive); a
// fragment without a percentage counts as 0. Same rule as the server's
// _evidence_above() in web/main.py.
export function reachesMinScore(relevancePercent: number | null | undefined, minScore: number): boolean {
  return minScore <= 0 || (relevancePercent ?? 0) >= minScore;
}

export function countReachingMinScore(fragments: FragmentItem[], minScore: number): number {
  return fragments.filter((fragment) => reachesMinScore(fragment.relevancePercent, minScore)).length;
}
