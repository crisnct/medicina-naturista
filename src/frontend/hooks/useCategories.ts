import { useQuery } from "@tanstack/react-query";
import { useEffect, useState, useRef, type SetStateAction } from "react";
import { api } from "../api/client";
import { readStoredSelection, storeSelection } from "../lib/categorySelection";
import { useLanguage, type Language } from "../lib/texts";

export function useCategories(enabled = true) {
  const language = useLanguage();
  const query = useQuery({
    queryKey: ["categories", language],
    // The tree of THIS language, whatever the current language is when the request runs.
    queryFn: () => api.getCategories(language),
    retry: false,
    enabled,
  });
  const data = query.data;
  const [selections, setSelections] = useState<Record<Language, Set<string>>>(() => ({
    ro: new Set(),
    en: new Set(),
  }));
  const latest = useRef(selections);
  latest.current = selections;
  const seeded = useRef(new Set<Language>());
  useEffect(() => {
    if (!data) return;
    const known = new Set(data.defaultSelection);
    const first = !seeded.current.has(language);
    seeded.current.add(language);
    // The first time a language is shown: what the patient ticked in it before (this tab or an
    // earlier visit), else every source. Afterwards: what is ticked now.
    const remembered = first ? readStoredSelection(language) : null;
    setSelections((previous) => ({
      ...previous,
      [language]: first && remembered === null
        ? known
        : new Set([...(remembered ?? previous[language])].filter((id) => known.has(id))),
    }));
  }, [language, data]);
  return {
    isLoading: query.isPending,
    tree: data?.tree ?? null,
    documentCount: data?.tree?.totalDocuments ?? null,
    conditionCount: data?.conditionCount ?? null,
    herbCount: data?.herbCount ?? null,
    selected: selections[language],
    setSelected: (value: SetStateAction<Set<string>>) => {
      const current = latest.current[language];
      const next = typeof value === "function" ? value(current) : value;
      storeSelection(language, next);
      setSelections((previous) => ({ ...previous, [language]: next }));
    },
  };
}
