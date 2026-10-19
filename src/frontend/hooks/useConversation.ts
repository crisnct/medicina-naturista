import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { api, ApiError, errorMessage, isSessionUnavailable } from "../api/client";
import type { ChatMessage, ReportModel, SearchSignals, ResourceInvalidations, SessionResponse } from "../api/types";

import { reconcileRetention } from "../lib/retention";
import type { GenerationFeedback } from "../lib/generationFeedback";
import { useReportGeneration } from "./useReportGeneration";

const SESSION_KEY = ["session"] as const;
const REPORT_MODELS_KEY = ["report-models"] as const;

class AcceptedMessageError extends Error {
  constructor(readonly original: unknown) {
    super("Message accepted, processing failed");
  }
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
  const reportModelsQuery = useQuery({
    queryKey: REPORT_MODELS_KEY,
    queryFn: api.getReportModels,
    retry: false,
    // Authorization may change in the separate owner tab.
    refetchOnWindowFocus: "always",
  });

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

  const generation = useReportGeneration(sessionQuery.data, setGenerationFeedback, setNeedsSessionRecovery, setBanner);
  const sessionError = sessionQuery.error;
  const sessionErrorMessage = sessionError instanceof ApiError && sessionError.code === "RATE_LIMIT"
    ? `Ați deschis prea multe conversații într-un minut. ${sessionError.retryAfter
      ? `Așteptați ${sessionError.retryAfter} de secunde, apoi apăsați „Verifică din nou”.`
      : "Așteptați un minut, apoi apăsați „Verifică din nou”."}`
    : sessionError ? errorMessage(sessionError, "Sesiunea nu a putut fi încărcată.") : null;

  const visibleGenerationFeedback = { ...generationFeedback };
  for (const [searchId, feedback] of Object.entries(generation.feedback)) {
    // Keep retained text without hiding an error from starting a new attempt.
    visibleGenerationFeedback[searchId] = feedback.terminal
      ? { ...feedback, ...visibleGenerationFeedback[searchId] }
      : feedback;
  }

  const reportModels = reportModelsQuery.data?.models ?? [];
  const defaultReportModel = reportModelsQuery.data?.defaultModel ?? reportModels[0];
  const allowedReportModels = reportModelsQuery.data?.allowedModels
    ?? [];

  return {
    history: history.map((message) => message.kind === "generate" ? { ...message, busy: generation.activeSearches.has(message.searchId) } : message),
    reportModels,
    defaultReportModel,
    allowedReportModels,
    latestReportId: sessionQuery.data?.latestReportId,
    generationFeedback: visibleGenerationFeedback,
    isLoading: sessionQuery.isLoading,
    isError: sessionQuery.isError,
    sessionError: sessionErrorMessage,
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
    isGenerating: generation.isGenerating,
    generateReport: (searchId: string, minScore: number, model: ReportModel | undefined = defaultReportModel) => {
      if (model && allowedReportModels.includes(model)) generation.generate(searchId, minScore, model);
    },
  };
}
