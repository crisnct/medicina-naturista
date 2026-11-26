import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { LocalModel } from "../api/types";

const LOCAL_MODELS_KEY = ["local-models"];

// The server caches one answer for every visitor for 3 s, so asking more often gains nothing.
// TanStack Query pauses the interval while the tab is hidden.
export const LOCAL_MODELS_REFRESH_MS = 3000;

export function useLocalModels() {
  return useQuery({
    queryKey: LOCAL_MODELS_KEY,
    queryFn: ({ signal }) => api.getLocalModels(signal),
    refetchInterval: LOCAL_MODELS_REFRESH_MS,
    retry: false,
  });
}

// The admin's unload; the answer is the window's fresh state, shown at once.
export function useUnloadLocalModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (model: LocalModel) => api.unloadLocalModel(model.runtime, model.id),
    onSuccess: (state) => queryClient.setQueryData(LOCAL_MODELS_KEY, state),
  });
}
