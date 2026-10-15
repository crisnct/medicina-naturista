import { useQuery } from "@tanstack/react-query";
import { useEffect, useState, useRef } from "react";
import { api } from "../api/client";

export function useCategories(enabled = true) {
  const query = useQuery({ queryKey: ["categories"], queryFn: api.getCategories, retry: false, enabled });
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const seeded = useRef(false);

  // Seed the selection with "every known category" the first time the tree
  // loads — matching the panel's own default (every checkbox starts checked).
  useEffect(() => {
    if (query.data) {
      if (!seeded.current) {
        seeded.current = true;
        setSelected(new Set(query.data.defaultSelection));
      } else {
        const known = new Set(query.data.defaultSelection);
        setSelected((previous) => new Set([...previous].filter((id) => known.has(id))));
      }
    }
  }, [query.data]);

  return {
    isLoading: query.isPending,
    tree: query.data?.tree ?? null,
    selected,
    setSelected,
  };
}
