import { tr } from "../lib/texts";
import { useEffect, useState } from "react";
import { DoctorAvatar } from "./DoctorAvatar";

// A slow status ring and elapsed time while retrieval or report generation is pending.
export function TypingIndicator({ label, paused = false, startedAt }: {
  label?: string;
  paused?: boolean;
  // Unix seconds, captured by the backend when the report worker starts.
  startedAt?: number | null;
}) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const seconds = paused ? 0 : elapsedSeconds;
  const elapsedTime = `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}`;

  useEffect(() => {
    setElapsedSeconds(0);
    if (paused) return;
    const elapsedBeforeMount = startedAt == null ? 0 : Math.max(0, Date.now() - startedAt * 1000);
    const observedAt = performance.now();
    const update = () => setElapsedSeconds(Math.floor((elapsedBeforeMount + performance.now() - observedAt) / 1000));
    update();
    const interval = window.setInterval(update, 1000);
    return () => window.clearInterval(interval);
  }, [paused, startedAt]);

  return (
    <div className="message-wrap assistant">
      <div className="message typing-indicator" role="status" aria-live="polite">
        <DoctorAvatar />
        <span className="loader" aria-hidden="true" />
        {label && <span>{label}</span>}
        <span className="typing-elapsed">{tr("interface.typing_elapsed_prefix")}{elapsedTime}</span>
      </div>
    </div>
  );
}
