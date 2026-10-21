import { tr } from "./lib/texts";
import { useEffect } from "react";
import { Hero } from "./components/Hero";
import { ChatHistory } from "./components/ChatHistory";
import { Composer } from "./components/Composer";
import { CategoryFilterPanel } from "./components/CategoryFilterPanel";
import { OwnerNotice } from "./components/OwnerNotice";
import { useConversation } from "./hooks/useConversation";
import { useCategories } from "./hooks/useCategories";
import { useSearchSignals } from "./hooks/useSearchSignals";
import { useStartup } from "./hooks/useStartup";
import { api } from "./api/client";

export function App() {
  const conversation = useConversation();
  const startup = useStartup();
  const categories = useCategories(startup.ready);
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
    if (!startup.ready || categories.isLoading) return;
    conversation.clearBanner();
    conversation.sendMessage(message, Array.from(categories.selected), searchSignals.signals, onAccepted);
  };

  return (
    <div id="app-shell">
      <Hero />
      <div id="conversation-card">
        {startup.message && (
          <div className="startup-notice" role="status">
            {startup.initializing && <span className="loader" aria-hidden="true" />}
            <span>{startup.message}</span>
          </div>
        )}
        {conversation.isLoading ? (
          <p className="loading-notice">{tr("interface.app_loading_conversation")}</p>
        ) : conversation.isError ? (
          <div role="alert" className="loading-notice">
            <p>{conversation.sessionError ?? tr("interface.app_session_load_failed")}</p>
            <button type="button" onClick={conversation.retrySession}>{tr("interface.app_retry")}</button>
          </div>
        ) : (
          <ChatHistory
            history={conversation.history}
            pending={conversation.isSending}
            pendingLabel={conversation.isClassifying ? tr("interface.app_classifying") : conversation.isSearching ? tr("interface.app_searching") : tr("interface.app_sending_message")}
            onGenerate={conversation.generateReport}
            reportModels={conversation.reportModels}
            defaultReportModel={conversation.defaultReportModel}
            allowedReportModels={conversation.allowedReportModels}
            actionsDisabled={!startup.ready || conversation.needsSessionRecovery || conversation.isReconnecting || conversation.isSending || conversation.isGenerating}
            generationFeedback={conversation.generationFeedback}
          />
        )}
        <OwnerNotice message={conversation.banner} />
        {conversation.needsSessionRecovery && (
          <button type="button" className="secondary-button" disabled={conversation.isReconnecting} onClick={conversation.reconnectSession}>
            {conversation.isReconnecting ? tr("interface.app_reconnecting_session") : tr("interface.app_reconnect_session")}
          </button>
        )}
        {!conversation.isError && (
          <>
            <Composer disabled={!startup.ready || categories.isLoading || conversation.isLoading || conversation.isSending || conversation.isGenerating || conversation.needsSessionRecovery || conversation.isReconnecting} processing={conversation.isSending} onSend={handleSend} />
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
            <h3 id="source-information-title">{tr("interface.app_data_usage_title")}</h3>
            <p>{tr("interface.app_data_usage_notice")}</p>
          </aside>
        </footer>
      </div>
    </div>
  );
}
