import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

const LEARNING_KEY = ["learning"];

// The window reads the state every few seconds while it is open (plan 5.4b); the button's summary
// beside the chat needs it less often. TanStack Query pauses the interval while the tab is hidden.
export const LEARNING_REFRESH_OPEN_MS = 3000;
export const LEARNING_REFRESH_CLOSED_MS = 15000;

// Only the admin's button asks: anyone else gets 403.
export function useLearning(open: boolean) {
  return useQuery({
    queryKey: LEARNING_KEY,
    queryFn: ({ signal }) => api.getLearning(signal),
    refetchInterval: open ? LEARNING_REFRESH_OPEN_MS : LEARNING_REFRESH_CLOSED_MS,
    retry: false,
  });
}

// Level null means all levels; the answer is the fresh state, shown at once.
export function useStartLearning() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ level, includeLower }: { level: number | null; includeLower?: boolean }) =>
      api.startLearning(level, includeLower),
    onSuccess: (state) => queryClient.setQueryData(LEARNING_KEY, state),
  });
}

export function useStopLearning() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (level: number | null) => api.stopLearning(level),
    onSuccess: (state) => queryClient.setQueryData(LEARNING_KEY, state),
  });
}
