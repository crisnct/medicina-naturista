import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { tr, type Language } from "../lib/texts";
import { LanguageSelect } from "./LanguageSelect";

const ACKNOWLEDGED_KEY = "naturist_first_visit_notice";
const VALIDITY_MS = 365 * 24 * 60 * 60 * 1000;

// The stored value is the time of acceptance; the notice shows again once a year has passed.
function wasAcknowledged(): boolean {
  try {
    const acceptedAt = Number(window.localStorage.getItem(ACKNOWLEDGED_KEY));
    return acceptedAt > 0 && Date.now() - acceptedAt < VALIDITY_MS;
  } catch { return false; }
}

function remember() {
  try { window.localStorage.setItem(ACKNOWLEDGED_KEY, String(Date.now())); } catch { /* The notice simply shows again. */ }
}

// An information notice, not a cookie wall: nothing is tracked, and the only way on is to confirm
// that the medical warning and the data use were read. Shown in the interface language, with the
// same language switch as the page, and again after a year.
export function FirstVisitNotice({ language, languageDisabled, onLanguageChange }: {
  language: Language;
  languageDisabled?: boolean;
  onLanguageChange: (language: Language) => void;
}) {
  const [open, setOpen] = useState(() => !wasAcknowledged());
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closing = useRef(false);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!open || !dialog) return;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }, [open]);

  if (!open) return null;

  const confirm = () => {
    closing.current = true;
    remember();
    setOpen(false);
  };

  const points = [
    { icon: "🤖", label: tr("interface.app_data_usage_providers_label"), text: tr("interface.app_data_usage_providers_text") },
    { icon: "🔒", label: tr("interface.app_data_usage_storage_label"), text: tr("interface.app_data_usage_storage_text") },
    { icon: "🛡️", label: tr("interface.app_data_usage_gdpr_label"), text: tr("interface.app_data_usage_gdpr_text") },
    { icon: "🍪", label: tr("interface.first_visit_cookies_label"), text: tr("interface.first_visit_cookies_text") },
  ];

  return createPortal(
    <dialog
      ref={dialogRef}
      className="first-visit-dialog"
      lang={language}
      aria-labelledby="first-visit-title"
      // Escape must not skip the notice; only the button confirms it.
      onCancel={(event) => event.preventDefault()}
      onClose={(event) => {
        const dialog = event.currentTarget;
        if (!closing.current && dialog.isConnected && !dialog.open) dialog.showModal();
      }}
    >
      <div className="first-visit-header">
        <h2 id="first-visit-title">{tr("interface.first_visit_title")}</h2>
        <div className="language-selector">
          <span id="first-visit-language-label">{language === "en" ? "Limbă" : "Language"}</span>
          <LanguageSelect id="first-visit-language" value={language} labelId="first-visit-language-label"
            disabled={languageDisabled} onChange={onLanguageChange} />
        </div>
      </div>
      <p className="source-important">
        <strong>⚕️ {tr("interface.app_data_usage_medical_label")}</strong>{tr("interface.app_data_usage_medical_text")}
      </p>
      <ul className="source-points">
        {points.map((point) => (
          <li key={point.icon}>
            <span className="source-point-icon" aria-hidden="true">{point.icon}</span>
            <div><strong>{point.label}</strong>{point.text}</div>
          </li>
        ))}
      </ul>
      <button type="button" className="first-visit-confirm" autoFocus onClick={confirm}>
        {tr("interface.first_visit_button")}
      </button>
    </dialog>,
    document.body,
  );
}
