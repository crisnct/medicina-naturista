import { tr } from "../lib/texts";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function useStartup() {
  const query = useQuery({
    queryKey: ["startup"],
    queryFn: api.getStartup,
    retry: false,
    refetchInterval: (current) => current.state.error || current.state.data?.status === "initializing" ? 1000 : false,
    refetchOnWindowFocus: "always",
  });

  return {
    ready: !query.isError && (query.data?.status === "ready" || query.data?.status === "degraded"),
    initializing: !query.isError && (!query.data || query.data.status === "initializing"),
    message: query.isError ? tr("interface.startup_reconnecting")
      : query.data?.message ?? (query.isPending ? tr("interface.startup_initializing") : null),
  };
}
