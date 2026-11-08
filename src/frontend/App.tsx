import { applyDocumentLanguage, setLanguage, useLanguage, tr, type Language } from "./lib/texts";
import { useEffect, useState } from "react";
import { Hero } from "./components/Hero";
import { ChatHistory } from "./components/ChatHistory";
import { Composer } from "./components/Composer";
import { CategoryFilterPanel } from "./components/CategoryFilterPanel";
import { LanguageSelect } from "./components/LanguageSelect";
import { OwnerNotice } from "./components/OwnerNotice";
import { FirstVisitNotice } from "./components/FirstVisitNotice";
import { useConversation } from "./hooks/useConversation";
import { useCategories } from "./hooks/useCategories";
import { useSearchSignals } from "./hooks/useSearchSignals";
import { useStartup } from "./hooks/useStartup";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "./api/client";

export function App() {
  const language = useLanguage();
  const queryClient = useQueryClient();
  const [changingLanguage, setChangingLanguage] = useState(false);
  const [languageError, setLanguageError] = useState(false);
  const conversation = useConversation();
  const startup = useStartup();
  const categories = useCategories(startup.ready);
  const searchSignals = useSearchSignals();

  useEffect(() => { applyDocumentLanguage(); }, []);

  const changeLanguage = async (next: Language) => {
    if (next === language) return;
    setChangingLanguage(true);
    setLanguageError(false);
    try {
      await api.changeLanguage(next);
      setLanguage(next);
      conversation.clearBanner();
      await queryClient.invalidateQueries({ queryKey: ["categories"] });
    } catch {
      setLanguageError(true);
    } finally {
      setChangingLanguage(false);
    }
  };

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
    if (!startup.ready || categories.isLoading || changingLanguage) return;
    conversation.clearBanner();
    conversation.sendMessage(message, Array.from(categories.selected), searchSignals.signals, onAccepted);
  };

  return (
    <div id="app-shell">
      <FirstVisitNotice />
      <Hero documentCount={categories.documentCount ?? conversation.documentCounts?.[language] ?? null} controls={<div className="language-selector">
        <span id="application-language-label">{language === "en" ? "Limbă" : "Language"}</span>
        <LanguageSelect value={language} labelId="application-language-label"
          disabled={changingLanguage || conversation.isLoading || conversation.isSending || conversation.isGenerating || conversation.isReconnecting || !startup.ready}
          onChange={(next) => void changeLanguage(next)} />
      </div>} />
      {languageError && <p role="alert">{tr("interface.api_unexpected_error")}</p>}
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
            effortReportModels={conversation.effortReportModels}
            generationLimitDefaults={conversation.generationLimitDefaults}
            reportModelDetails={conversation.reportModelDetails}
            actionsDisabled={changingLanguage || !startup.ready || conversation.needsSessionRecovery || conversation.isReconnecting || conversation.isSending || conversation.isGenerating}
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
            <Composer disabled={changingLanguage || !startup.ready || categories.isLoading || conversation.isLoading || conversation.isSending || conversation.isGenerating || conversation.needsSessionRecovery || conversation.isReconnecting} processing={conversation.isSending} onSend={handleSend} />
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
            <ul className="source-points">
              <li>
                <span className="source-point-icon" aria-hidden="true">📚</span>
                <div><strong>{tr("interface.app_data_usage_sources_label")}</strong>{tr("interface.app_data_usage_sources_text")}</div>
              </li>
              <li>
                <span className="source-point-icon" aria-hidden="true">🤖</span>
                <div><strong>{tr("interface.app_data_usage_providers_label")}</strong>{tr("interface.app_data_usage_providers_text")}</div>
              </li>
              <li>
                <span className="source-point-icon" aria-hidden="true">🔒</span>
                <div><strong>{tr("interface.app_data_usage_storage_label")}</strong>{tr("interface.app_data_usage_storage_text")}</div>
              </li>
              <li>
                <span className="source-point-icon" aria-hidden="true">🛡️</span>
                <div><strong>{tr("interface.app_data_usage_gdpr_label")}</strong>{tr("interface.app_data_usage_gdpr_text")}</div>
              </li>
            </ul>
            <p className="source-important">
              <strong>⚕️ {tr("interface.app_data_usage_medical_label")}</strong>{tr("interface.app_data_usage_medical_text")}
            </p>
          </aside>
        </footer>
      </div>
    </div>
  );
}
