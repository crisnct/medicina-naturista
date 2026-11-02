import { useCallback, useSyncExternalStore } from "react";

// The "Scor minim" chosen for a search, shared by its fragments filter and by the
// generation options below it, so choosing it in one place applies to the other.
const scores = new Map<string, number>();
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function useMinScore(searchId: string): [number, (value: number) => void] {
  const value = useSyncExternalStore(subscribe, () => scores.get(searchId) ?? 0);
  const setValue = useCallback((next: number) => {
    scores.set(searchId, next);
    listeners.forEach((listener) => listener());
  }, [searchId]);
  return [value, setValue];
}
