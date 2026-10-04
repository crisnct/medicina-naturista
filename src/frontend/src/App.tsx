import { useEffect } from "react";
import { Hero } from "./components/Hero";
import { AssistantHeader } from "./components/AssistantHeader";
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
    window.addEventListener("pagehide", handlePageHide);
    return () => window.removeEventListener("pagehide", handlePageHide);
  }, []);

  const handleSend = (message: string) => {
    conversation.clearBanner();
    conversation.sendMessage(message, Array.from(categories.selected), searchSignals.signals);
  };

  return (
    <div id="app-shell">
      <Hero />
      <div id="conversation-card">
        <div id="chat-header">
          <AssistantHeader />
        </div>
        {conversation.isLoading ? (
          <p className="loading-notice">Se încarcă discuția...</p>
        ) : conversation.isError ? (
          <p className="loading-notice">
            Nu am putut încărca sesiunea. Reîncărcați pagina.
          </p>
        ) : (
          <ChatHistory
            history={conversation.history}
            pending={conversation.isSearching || conversation.isGenerating}
            onGenerate={conversation.generateReport}
          />
        )}
        <OwnerNotice message={conversation.banner} />
        <Composer disabled={conversation.isSending} processing={conversation.isSending} onSend={handleSend} />
        <CategoryFilterPanel
          tree={categories.tree}
          selected={categories.selected}
          onChange={categories.setSelected}
          signals={searchSignals.signals}
          onSignalsChange={searchSignals.setSignals}
        />
      </div>
    </div>
  );
}
