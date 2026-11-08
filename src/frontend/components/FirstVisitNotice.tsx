import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { trIn, type Language } from "../lib/texts";

const ACKNOWLEDGED_KEY = "naturist_first_visit_notice";
const LANGUAGES: Language[] = ["ro", "en"];

function wasAcknowledged(): boolean {
  try { return window.localStorage.getItem(ACKNOWLEDGED_KEY) === "1"; } catch { return false; }
}

function remember() {
  try { window.localStorage.setItem(ACKNOWLEDGED_KEY, "1"); } catch { /* The notice simply shows again. */ }
}

// One language of the notice. Both are always shown, side by side, whatever the interface language is.
function NoticeColumn({ lang }: { lang: Language }) {
  const points = [
    { icon: "🤖", label: trIn(lang, "interface.app_data_usage_providers_label"), text: trIn(lang, "interface.app_data_usage_providers_text") },
    { icon: "🔒", label: trIn(lang, "interface.app_data_usage_storage_label"), text: trIn(lang, "interface.app_data_usage_storage_text") },
    { icon: "🛡️", label: trIn(lang, "interface.app_data_usage_gdpr_label"), text: trIn(lang, "interface.app_data_usage_gdpr_text") },
    { icon: "🍪", label: trIn(lang, "interface.first_visit_cookies_label"), text: trIn(lang, "interface.first_visit_cookies_text") },
  ];
  return (
    <section className="first-visit-column" lang={lang} aria-labelledby={`first-visit-title-${lang}`}>
      <h2 id={`first-visit-title-${lang}`}>{trIn(lang, "interface.first_visit_title")}</h2>
      <p className="source-important">
        <strong>⚕️ {trIn(lang, "interface.app_data_usage_medical_label")}</strong>{trIn(lang, "interface.app_data_usage_medical_text")}
      </p>
      <ul className="source-points">
        {points.map((point) => (
          <li key={point.icon}>
            <span className="source-point-icon" aria-hidden="true">{point.icon}</span>
            <div><strong>{point.label}</strong>{point.text}</div>
          </li>
        ))}
      </ul>
    </section>
  );
}

// An information notice, not a cookie wall: nothing is tracked, and the only way on is to confirm
// that the medical warning and the data use were read. Shown once per browser, in both languages.
export function FirstVisitNotice() {
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

  return createPortal(
    <dialog
      ref={dialogRef}
      className="first-visit-dialog"
      aria-labelledby="first-visit-title-ro first-visit-title-en"
      // Escape must not skip the notice; only the button confirms it.
      onCancel={(event) => event.preventDefault()}
      onClose={(event) => {
        const dialog = event.currentTarget;
        if (!closing.current && dialog.isConnected && !dialog.open) dialog.showModal();
      }}
    >
      <div className="first-visit-columns">
        {LANGUAGES.map((lang) => <NoticeColumn key={lang} lang={lang} />)}
      </div>
      <button type="button" className="first-visit-confirm" autoFocus onClick={confirm}>
        {LANGUAGES.map((lang) => trIn(lang, "interface.first_visit_button")).join(" / ")}
      </button>
    </dialog>,
    document.body,
  );
}
