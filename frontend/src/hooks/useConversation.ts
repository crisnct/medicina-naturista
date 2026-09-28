import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { api } from "../api/client";
import type { ChatMessage, GenerateMessage } from "../api/types";

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

  const sessionQuery = useQuery({ queryKey: SESSION_KEY, queryFn: api.getSession });
  const history = sessionQuery.data?.history ?? [];

  const appendMessages = useCallback(
    (messages: ChatMessage[]) => {
      queryClient.setQueryData(SESSION_KEY, (old: { history: ChatMessage[] } | undefined) => ({
        history: [...(old?.history ?? []), ...messages],
      }));
    },
    [queryClient],
  );

  const sendMessage = useMutation({
    mutationFn: ({ message, categories }: { message: string; categories: string[] }) =>
      api.sendMessage(message, categories),
    onSuccess: (result) => appendMessages(result.messages),
    onError: () => setBanner("Mesajul nu a putut fi trimis. Încercați din nou."),
  });

  const generateReport = useMutation({
    mutationFn: (searchId: string) => api.generateReport(searchId),
    onMutate: (searchId) => {
      queryClient.setQueryData(SESSION_KEY, (old: { history: ChatMessage[] } | undefined) =>
        old ? { history: setBusy(old.history, searchId, true) } : old,
      );
    },
    onSuccess: (result, searchId) => {
      if (result.ownerNotice) {
        setBanner(result.ownerNotice);
        queryClient.setQueryData(SESSION_KEY, (old: { history: ChatMessage[] } | undefined) =>
          old ? { history: setBusy(old.history, searchId, false) } : old,
        );
        return;
      }
      queryClient.setQueryData(SESSION_KEY, (old: { history: ChatMessage[] } | undefined) => {
        if (!old) return old;
        const replaced = replaceGenerateMessage(old.history, searchId, result.messages);
        // No matching "generate" message left in place (e.g. generation
        // failed and only an error text was appended) — append instead.
        const stillPending = old.history.some(
          (message): message is GenerateMessage => message.kind === "generate" && message.searchId === searchId,
        );
        return { history: stillPending ? replaced : [...setBusy(old.history, searchId, false), ...result.messages] };
      });
    },
    onError: (_error, searchId) => {
      setBanner("Rețeta nu a putut fi generată. Încercați din nou.");
      queryClient.setQueryData(SESSION_KEY, (old: { history: ChatMessage[] } | undefined) =>
        old ? { history: setBusy(old.history, searchId, false) } : old,
      );
    },
  });

  return {
    history,
    isLoading: sessionQuery.isLoading,
    isError: sessionQuery.isError,
    banner,
    clearBanner: () => setBanner(null),
    sendMessage: (message: string, categories: string[]) => sendMessage.mutate({ message, categories }),
    isSending: sendMessage.isPending,
    generateReport: (searchId: string) => generateReport.mutate(searchId),
  };
}
