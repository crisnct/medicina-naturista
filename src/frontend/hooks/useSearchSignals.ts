import { useCallback, useState } from "react";
import type { SearchSignals } from "../api/types";
import { countOn, readStoredSignals, storeSignals } from "../lib/searchSignals";

// The signals chosen for the next search, remembered across visits. A change
// that would leave no signal on is ignored, so the state never reaches zero.
export function useSearchSignals() {
  const [signals, setSignalsState] = useState<SearchSignals>(readStoredSignals);

  const setSignals = useCallback((next: SearchSignals) => {
    if (countOn(next) === 0) return;
    setSignalsState(next);
    storeSignals(next);
  }, []);

  return { signals, setSignals };
}
