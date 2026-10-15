import { useEffect } from "react";
import { Hero } from "./components/Hero";
import { ChatHistory } from "./components/ChatHistory";
import { Composer } from "./components/Composer";
import { CategoryFilterPanel } from "./components/CategoryFilterPanel";
import { OwnerNotice } from "./components/OwnerNotice";
import { useConversation } from "./hooks/useConversation";
import { useCategories } from "./hooks/useCategories";
import { useSearchSignals } from "./hooks/useSearchSignals";
import { api } from "./api/client";

export function App() {
  const conversation = useConversation();
  const categories = useCategories();
  const searchSignals = useSearchSignals();

  useEffect(() => {
    const handlePageHide = () => api.unloadSession();
    const handlePageShow = (event: PageTransitionEvent) => {
      if (event.persisted) window.location.reload();
    };
    window.addEventListener("pagehide", handlePageHide);
    window.addEventListener("pageshow", handlePageShow);
    return () => {
      window.removeEventListener("pagehide", handlePageHide);
      window.removeEventListener("pageshow", handlePageShow);
    };
  }, []);

  const handleSend = (message: string, onAccepted: () => void) => {
    conversation.clearBanner();
    conversation.sendMessage(message, Array.from(categories.selected), searchSignals.signals, onAccepted);
  };

  return (
    <div id="app-shell">
      <Hero />
      <div id="conversation-card">
        {conversation.isLoading ? (
          <p className="loading-notice">Se încarcă discuția...</p>
        ) : conversation.isError ? (
          <div role="alert" className="loading-notice">
            <p>{conversation.sessionError ?? "Nu am putut încărca sesiunea. Reîncărcați pagina."}</p>
            <button type="button" onClick={conversation.retrySession}>Verifică din nou</button>
          </div>
        ) : (
          <ChatHistory
            history={conversation.history}
            pending={conversation.isSending}
            pendingLabel={conversation.isClassifying ? "Înțeleg întrebarea…" : conversation.isSearching ? "Caut informații în bibliotecă…" : "Trimit mesajul…"}
            onGenerate={conversation.generateReport}
            reportModels={conversation.reportModels}
            actionsDisabled={conversation.needsSessionRecovery || conversation.isReconnecting || conversation.isSending || conversation.isGenerating}
            generationFeedback={conversation.generationFeedback}
          />
        )}
        <OwnerNotice message={conversation.banner} />
        {conversation.needsSessionRecovery && (
          <button type="button" className="secondary-button" disabled={conversation.isReconnecting} onClick={conversation.reconnectSession}>
            {conversation.isReconnecting ? "Reconectez sesiunea…" : "Reconectează sesiunea"}
          </button>
        )}
        {!conversation.isError && (
          <>
            <Composer disabled={conversation.isLoading || conversation.isSending || conversation.isGenerating || conversation.needsSessionRecovery || conversation.isReconnecting} processing={conversation.isSending} onSend={handleSend} />
            <CategoryFilterPanel
              tree={categories.tree}
              selected={categories.selected}
              onChange={categories.setSelected}
              signals={searchSignals.signals}
              onSignalsChange={searchSignals.setSignals}
            />
          </>
        )}
        <footer className="source-notice">
          <aside className="source-information" aria-labelledby="source-information-title">
            <h3 id="source-information-title">ℹ️ Despre surse și utilizarea datelor</h3>
            <p>Căutarea folosește cărțile și documentele din biblioteca naturistă. Pentru înțelegerea întrebării și redactarea raportului, aplicația poate trimite mesajele și fragmentele selectate unor furnizori AI externi.</p>
          </aside>
        </footer>
      </div>
    </div>
  );
}
