import { tr } from "../lib/texts";
import type { DownloadMessage } from "../api/types";
import { DoctorAvatar } from "./DoctorAvatar";

export function DownloadPanel({ message }: { message: DownloadMessage }) {
  return (
    <section className="report-ready-panel" role="status" aria-live="polite">
      <div className="report-ready-copy">
        <DoctorAvatar />
        <span className="report-ready-icon" aria-hidden="true">{"✅"}</span>
        <span>
          <strong>{tr("interface.download_ready")}</strong>
          <small>{tr("interface.download_hint")}</small>
        </span>
      </div>
      <div className="report-actions">
        <a
          href={message.url}
          download={message.filename}
          className="pdf-download"
          aria-label={tr("interface.download_pdf_label")}
        >
          <span aria-hidden="true">{"📄"}</span> {tr("interface.download_pdf")}</a>
      </div>
    </section>
  );
}
