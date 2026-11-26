import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

// The server caches one answer for every visitor for 3 s, so asking more often gains nothing.
// TanStack Query pauses the interval while the tab is hidden.
export const LOCAL_MODELS_REFRESH_MS = 3000;

export function useLocalModels() {
  return useQuery({
    queryKey: ["local-models"],
    queryFn: ({ signal }) => api.getLocalModels(signal),
    refetchInterval: LOCAL_MODELS_REFRESH_MS,
    retry: false,
  });
}
