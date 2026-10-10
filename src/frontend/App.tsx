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

  const handleSend = (message: string) => {
    conversation.clearBanner();
    conversation.sendMessage(message, Array.from(categories.selected), searchSignals.signals);
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
            pending={conversation.isSearching || conversation.isGenerating}
            onGenerate={conversation.generateReport}
          />
        )}
        <OwnerNotice message={conversation.banner} />
        {!conversation.isError && (
          <>
            <Composer disabled={conversation.isLoading || conversation.isSending} processing={conversation.isSending} onSend={handleSend} />
            <CategoryFilterPanel
              tree={categories.tree}
              selected={categories.selected}
              onChange={categories.setSelected}
              signals={searchSignals.signals}
              onSignalsChange={searchSignals.setSignals}
            />
          </>
        )}
      </div>
    </div>
  );
}
