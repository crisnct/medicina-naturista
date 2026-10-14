import { useEffect, useState } from "react";
import { DoctorAvatar } from "./DoctorAvatar";

// A slow status ring and elapsed time while retrieval or report generation is pending.
export function TypingIndicator({ label }: { label?: string }) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    const startedAt = Date.now();
    const interval = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(interval);
  }, []);

  return (
    <div className="message-wrap assistant">
      <div className="message typing-indicator" role="status" aria-live="polite">
        <DoctorAvatar />
        <span className="loader" aria-hidden="true" />
        {label && <span>{label}</span>}
        <span className="typing-elapsed">Timp scurs: {elapsedSeconds}s</span>
      </div>
    </div>
  );
}
