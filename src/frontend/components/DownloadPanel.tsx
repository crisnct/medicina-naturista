import type { DownloadMessage } from "../api/types";

export function DownloadPanel({ message }: { message: DownloadMessage }) {
  return (
    <section className="report-ready-panel" role="status" aria-live="polite">
      <div className="report-ready-copy">
        <span className="report-ready-icon" aria-hidden="true">✅</span>
        <span>
          <strong>Raportul complet este gata</strong>
          <small>Îl puteți salva pentru a-l consulta oricând.</small>
        </span>
      </div>
      <a
        href={message.url}
        download={message.filename}
        className="pdf-download"
        aria-label="Descarcă raportul complet în format PDF"
      >
        <span aria-hidden="true">📄</span> Descarcă PDF
      </a>
    </section>
  );
}
