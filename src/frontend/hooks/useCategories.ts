import { useQuery } from "@tanstack/react-query";
import { useEffect, useState, useRef, type SetStateAction } from "react";
import { api } from "../api/client";
import { useLanguage, type Language } from "../lib/texts";

export function useCategories(enabled = true) {
  const language = useLanguage();
  const query = useQuery({
    queryKey: ["categories", language],
    queryFn: api.getCategories,
    retry: false,
    enabled,
  });
  const [selections, setSelections] = useState<Record<Language, Set<string>>>(() => ({
    ro: new Set(),
    en: new Set(),
  }));
  const seeded = useRef(new Set<Language>());
  useEffect(() => {
    if (!query.data) return;
    const known = new Set(query.data.defaultSelection);
    const first = !seeded.current.has(language);
    seeded.current.add(language);
    setSelections((previous) => ({
      ...previous,
      [language]: first ? known : new Set([...previous[language]].filter((id) => known.has(id))),
    }));
  }, [language, query.data]);
  return {
    isLoading: query.isPending,
    tree: query.data?.tree ?? null,
    selected: selections[language],
    setSelected: (value: SetStateAction<Set<string>>) => setSelections((previous) => ({
      ...previous,
      [language]: typeof value === "function" ? value(previous[language]) : value,
    })),
  };
}
