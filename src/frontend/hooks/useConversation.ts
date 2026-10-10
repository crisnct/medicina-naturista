import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { api, errorMessage } from "../api/client";
import type { ChatMessage, SearchSignals, ResourceInvalidations } from "../api/types";

import { reconcileRetention } from "../lib/retention";

const SESSION_KEY = ["session"] as const;

// Splice `replacements` in place of the "generate" message for searchId, or
// just flip its busy flag when there is nothing to replace it with yet —
// the same operation web/handlers.py's _replace_generate_message performs
// server-side, mirrored here for the optimistic local update.
function replaceGenerateMessage(
  history: ChatMessage[],
  searchId: string,
  replacements: ChatMessage[] | null,
): ChatMessage[] {
  const index = history.findIndex((message) => message.kind === "generate" && message.searchId === searchId);
  if (index === -1) return history;
  if (replacements === null) return history;
  const next = [...history];
  next.splice(index, 1, ...replacements);
  return next;
}

function setBusy(history: ChatMessage[], searchId: string, busy: boolean): ChatMessage[] {
  return history.map((message) =>
    message.kind === "generate" && message.searchId === searchId ? { ...message, busy } : message,
  );
}

export function useConversation() {
  const queryClient = useQueryClient();
  const [banner, setBanner] = useState<string | null>(null);
  // True while POST /api/search is in flight — separate from the send
  // mutation's own isPending (which also covers the fast first phase), so
  // the chat can show a "thinking" indicator only for the slow part.
  const [isSearching, setIsSearching] = useState(false);

  const sessionQuery = useQuery({ queryKey: SESSION_KEY, queryFn: api.getSession, retry: false });
  const history = sessionQuery.data?.history ?? [];

  const appendMessages = useCallback(
    (messages: ChatMessage[], result: ResourceInvalidations = {}) => {
      queryClient.setQueryData(SESSION_KEY, (old: { history: ChatMessage[] } | undefined) => ({
        history: reconcileRetention([...(old?.history ?? []), ...messages], result),
      }));
    },
    [queryClient],
  );

  const sendMessage = useMutation({
    // Two round trips, not one: append the fast phase's messages (the
    // patient's own text + the "Caut rapid..." notice) as soon as they
    // arrive, then run the slower retrieval separately — otherwise the
    // whole exchange would stay invisible until retrieval finished, which
    // reads as "my message didn't send" while the search is still running.
    mutationFn: async ({
      message,
      categories,
      signals,
    }: {
      message: string;
      categories: string[];
      signals: SearchSignals;
    }) => {
      const first = await api.sendMessage(message, categories, signals);
      appendMessages(first.messages, first);
      if (first.startSearch) {
        setIsSearching(true);
        try {
          let startSearch = true;
          if (first.identifyCondition) {
            const condition = await api.identifyCondition(first.contextRevision);
            appendMessages(condition.messages, condition);
            startSearch = condition.startSearch;
          }
          if (startSearch) {
            const second = await api.search(first.contextRevision);
            appendMessages(second.messages, second);
          }
        } finally {
          setIsSearching(false);
        }
      }
    },
    retry: false,
    onError: (error) => setBanner(errorMessage(error, "Mesajul nu a putut fi trimis. Încercați din nou.")),
  });

  const generateReport = useMutation({
    mutationFn: ({ searchId, minScore }: { searchId: string; minScore: number }) =>
      api.generateReport(searchId, minScore),
    onMutate: ({ searchId }) => {
      queryClient.setQueryData(SESSION_KEY, (old: { history: ChatMessage[] } | undefined) =>
        old ? { history: setBusy(old.history, searchId, true) } : old,
      );
    },
    onSuccess: (result, { searchId }) => {
      if (result.ownerNotice) {
        setBanner(result.ownerNotice);
        queryClient.setQueryData(SESSION_KEY, (old: { history: ChatMessage[] } | undefined) =>
          old ? { history: setBusy(old.history, searchId, false) } : old,
        );
        return;
      }
      queryClient.setQueryData(SESSION_KEY, (old: { history: ChatMessage[] } | undefined) => {
        if (!old) return old;
        // Only a finished report (it carries the download link) replaces the
        // "generate" call to action. On a failure the server answers with just
        // an error text and keeps the search pending, so the button stays,
        // re-enabled, below the error and the patient can retry.
        if (result.cancelled) return { history: setBusy(old.history, searchId, false) };
        const generated = result.messages.some((message) => message.kind === "download");
        if (!generated) return { history: reconcileRetention([...setBusy(old.history, searchId, false), ...result.messages], result) };
        return { history: reconcileRetention(replaceGenerateMessage(old.history, searchId, result.messages), result) };
      });
    },
    retry: false,
    onError: (error, { searchId }) => {
      setBanner(errorMessage(error, "Rețeta nu a putut fi generată. Încercați din nou."));
      queryClient.setQueryData(SESSION_KEY, (old: { history: ChatMessage[] } | undefined) =>
        old ? { history: setBusy(old.history, searchId, false) } : old,
      );
    },
  });

  return {
    history,
    isLoading: sessionQuery.isLoading,
    isError: sessionQuery.isError,
    sessionError: sessionQuery.error ? errorMessage(sessionQuery.error, "Sesiunea nu a putut fi încărcată.") : null,
    retrySession: () => { void sessionQuery.refetch(); },
    banner,
    clearBanner: () => setBanner(null),
    sendMessage: (message: string, categories: string[], signals: SearchSignals) =>
      sendMessage.mutate({ message, categories, signals }),
    isSending: sendMessage.isPending,
    isSearching,
    isGenerating: generateReport.isPending,
    generateReport: (searchId: string, minScore: number) => generateReport.mutate({ searchId, minScore }),
  };
}
