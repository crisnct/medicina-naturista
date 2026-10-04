import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api/client";

export function useCategories() {
  const query = useQuery({ queryKey: ["categories"], queryFn: api.getCategories });
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Seed the selection with "every known category" the first time the tree
  // loads — matching the panel's own default (every checkbox starts checked).
  useEffect(() => {
    if (query.data) setSelected(new Set(query.data.defaultSelection));
  }, [query.data]);

  return {
    tree: query.data?.tree ?? null,
    selected,
    setSelected,
  };
}
