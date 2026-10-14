import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { api, ApiError, errorMessage, isSessionUnavailable } from "../api/client";
import type { ChatMessage, SearchSignals, ResourceInvalidations, SessionResponse } from "../api/types";

import { reconcileRetention } from "../lib/retention";
import type { GenerationFeedback } from "../lib/generationFeedback";

const SESSION_KEY = ["session"] as const;

class AcceptedMessageError extends Error {
  constructor(readonly original: unknown) {
    super("Message accepted, processing failed");
  }
}

function setBusy(history: ChatMessage[], searchId: string, busy: boolean): ChatMessage[] {
  return history.map((message) =>
    message.kind === "generate" && message.searchId === searchId ? { ...message, busy } : message,
  );
}

export function useConversation() {
  const queryClient = useQueryClient();
  const [banner, setBanner] = useState<string | null>(null);
  const [needsSessionRecovery, setNeedsSessionRecovery] = useState(false);
  const [generationFeedback, setGenerationFeedback] = useState<Record<string, GenerationFeedback>>({});
  // True while POST /api/search is in flight — separate from the send
  // mutation's own isPending (which also covers the fast first phase), so
  // the chat can show a "thinking" indicator only for the slow part.
  const [isSearching, setIsSearching] = useState(false);
  const [isClassifying, setIsClassifying] = useState(false);

  const sessionQuery = useQuery({ queryKey: SESSION_KEY, queryFn: api.getSession, retry: false });
  const history = sessionQuery.data?.history ?? [];

  const reconnectSession = useMutation({
    mutationFn: api.getSession,
    retry: false,
    onSuccess: (session) => {
      queryClient.setQueryData(SESSION_KEY, session);
      setNeedsSessionRecovery(false);
      setGenerationFeedback({});
      setBanner("Sesiunea este conectată. Textul din câmp a fost păstrat; îl puteți trimite când doriți.");
    },
    onError: (error) => setBanner(errorMessage(error, "Sesiunea nu a putut fi reconectată. Încercați din nou.")),
  });

  const appendMessages = useCallback(
    (messages: ChatMessage[], result: ResourceInvalidations = {}) => {
      queryClient.setQueryData(SESSION_KEY, (old: SessionResponse | undefined) => ({
        ...old,
        history: reconcileRetention([...(old?.history ?? []), ...messages], result),
        latestReportId: result.evictedReportIds?.includes(old?.latestReportId ?? "") ? null : old?.latestReportId,
      }));
    },
    [queryClient],
  );

  const sendMessage = useMutation({
    // Echo immediately, classify, then continue only the selected branch.
    // Classification and retrieval have separate indicators and no automatic retries.
    mutationFn: async ({
      message,
      categories,
      signals,
      onAccepted,
    }: {
      message: string;
      categories: string[];
      signals: SearchSignals;
      onAccepted?: () => void;
    }) => {
      const first = await api.sendMessage(message, categories, signals);
      appendMessages(first.messages, first);
      if (first.cancelled) return;
      onAccepted?.();
      try {
        let routed = first;
        if (first.classifyMessage) {
          if (first.contextRevision === undefined) throw new Error("Missing message revision");
          setIsClassifying(true);
          try {
            routed = await api.classifyMessage(first.contextRevision);
            appendMessages(routed.messages, routed);
          } finally {
            setIsClassifying(false);
          }
        }
        if (routed.cancelled) return;
        if (routed.startSearch) {
          setIsSearching(true);
          try {
            let startSearch = true;
            if (routed.identifyCondition) {
              const condition = await api.identifyCondition(routed.contextRevision);
              appendMessages(condition.messages, condition);
              startSearch = condition.startSearch && !condition.cancelled;
            }
            if (startSearch) {
              const second = await api.search(routed.contextRevision);
              appendMessages(second.messages, second);
              if (second.removedCategoryIds?.length) {
                setBanner("Unele surse selectate nu mai există și au fost eliminate. Verificați selecția categoriilor.");
                void queryClient.invalidateQueries({ queryKey: ["categories"] });
              }
            }
          } finally {
            setIsSearching(false);
          }
        }
      } catch (error) {
        throw new AcceptedMessageError(error);
      }
    },
    retry: false,
    onError: (error) => {
      const original = error instanceof AcceptedMessageError ? error.original : error;
      if (isSessionUnavailable(original)) {
        setNeedsSessionRecovery(true);
        setBanner(error instanceof AcceptedMessageError
          ? "Mesajul a fost acceptat, dar sesiunea nu mai este disponibilă. Reconectați sesiunea; conversația anterioară poate să nu mai fie disponibilă. Mesajul nu va fi retrimis automat."
          : "Sesiunea nu mai este disponibilă, posibil după repornirea aplicației. Textul este păstrat. Reconectați sesiunea pentru a continua; conversația anterioară poate să nu mai fie disponibilă.");
        return;
      }
      const detail = errorMessage(original, "Încercați din nou.");
      setBanner(error instanceof AcceptedMessageError
        ? `Mesajul a fost acceptat, dar procesarea nu s-a încheiat. ${detail}`
        : `Mesajul nu a putut fi trimis. Textul este păstrat. ${detail}`);
      if (original instanceof ApiError && original.code === "CATEGORY_SELECTION_STALE") {
        void queryClient.invalidateQueries({ queryKey: ["categories"] });
      }
    },
  });

  const generateReport = useMutation({
    mutationFn: ({ searchId, minScore }: { searchId: string; minScore: number }) =>
      api.generateReport(searchId, minScore),
    onMutate: ({ searchId }) => {
      setGenerationFeedback((old) => {
        const next = { ...old };
        delete next[searchId];
        return next;
      });
      queryClient.setQueryData(SESSION_KEY, (old: SessionResponse | undefined) =>
        old ? { ...old, history: setBusy(old.history, searchId, true) } : old,
      );
    },
    onSuccess: (result, { searchId }) => {
      if (result.partial) setBanner("Raportul este parțial: unele recomandări nu au putut fi validate.");
      const ownerNotice = result.ownerNotice;
      if (ownerNotice) {
        setGenerationFeedback((old) => ({
          ...old, [searchId]: { message: ownerNotice, requiresAuthorization: true },
        }));
        queryClient.setQueryData(SESSION_KEY, (old: SessionResponse | undefined) =>
          old ? { ...old, history: setBusy(old.history, searchId, false) } : old,
        );
        return;
      }
      if (result.cancelled) {
        setGenerationFeedback((old) => ({
          ...old, [searchId]: { message: "Generarea a fost întreruptă. Raportul nu a fost salvat; puteți încerca din nou." },
        }));
      } else if (!result.messages.some((message) => message.kind === "download")) {
        const reply = result.messages
          .filter((message) => message.kind === "text" && message.role === "assistant")
          .map((message) => message.kind === "text" ? message.content : "")
          .join("\n");
        setGenerationFeedback((old) => ({
          ...old, [searchId]: { message: reply || "Raportul nu a putut fi generat. Încercați din nou." },
        }));
      }
      queryClient.setQueryData(SESSION_KEY, (old: SessionResponse | undefined) => {
        if (!old) return old;
        // Keep the reviewed fragments and generation controls in the conversation.
        // Failures remain inline; completed reports append to the existing history.
        if (result.cancelled) return { ...old, history: setBusy(old.history, searchId, false) };
        const generated = result.messages.find((message) => message.kind === "download");
        if (!generated) return { ...old, history: reconcileRetention(setBusy(old.history, searchId, false), result) };
        const retainedHistory = setBusy(old.history, searchId, false).filter((message) =>
          !(message.kind === "text" && message.generationSearchId === searchId),
        );
        return {
          ...old,
          latestReportId: generated.reportId,
          history: reconcileRetention([...retainedHistory, ...result.messages], result),
        };
      });
    },
    retry: false,
    onError: (error, { searchId }) => {
      if (isSessionUnavailable(error)) {
        setNeedsSessionRecovery(true);
        setBanner("Sesiunea nu mai este disponibilă. Reconectați sesiunea; căutările și rapoartele anterioare pot să nu mai fie disponibile.");
      } else {
        setGenerationFeedback((old) => ({
          ...old, [searchId]: { message: errorMessage(error, "Raportul nu a putut fi generat. Încercați din nou.") },
        }));
      }
      queryClient.setQueryData(SESSION_KEY, (old: SessionResponse | undefined) =>
        old ? { ...old, history: setBusy(old.history, searchId, false) } : old,
      );
    },
  });

  return {
    history,
    latestReportId: sessionQuery.data?.latestReportId,
    generationFeedback,
    isLoading: sessionQuery.isLoading,
    isError: sessionQuery.isError,
    sessionError: sessionQuery.error ? errorMessage(sessionQuery.error, "Sesiunea nu a putut fi încărcată.") : null,
    retrySession: () => { void sessionQuery.refetch(); },
    banner,
    needsSessionRecovery,
    isReconnecting: reconnectSession.isPending,
    reconnectSession: () => reconnectSession.mutate(),
    clearBanner: () => setBanner(null),
    sendMessage: (message: string, categories: string[], signals: SearchSignals, onAccepted?: () => void) =>
      sendMessage.mutate({ message, categories, signals, onAccepted }),
    isSending: sendMessage.isPending,
    isSearching,
    isClassifying,
    isGenerating: generateReport.isPending,
    generateReport: (searchId: string, minScore: number) => generateReport.mutate({ searchId, minScore }),
  };
}
