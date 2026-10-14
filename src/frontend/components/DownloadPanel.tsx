import type { DownloadMessage } from "../api/types";
import { DoctorAvatar } from "./DoctorAvatar";

export function DownloadPanel({ message }: { message: DownloadMessage }) {
  return (
    <section className="report-ready-panel" role="status" aria-live="polite">
      <div className="report-ready-copy">
        <DoctorAvatar />
        <span className="report-ready-icon" aria-hidden="true">✅</span>
        <span>
          <strong>Raportul este gata</strong>
          <small>Îl puteți salva pentru a-l consulta oricând.</small>
        </span>
      </div>
      <div className="report-actions">
        <a
          href={message.url}
          download={message.filename}
          className="pdf-download"
          aria-label="Descarcă raportul în format PDF"
        >
          <span aria-hidden="true">📄</span> Descarcă PDF
        </a>
      </div>
    </section>
  );
}
