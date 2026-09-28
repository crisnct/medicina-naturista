import { useEffect, useState } from "react";

// Animated "thinking" bubble shown while a slow backend call is in flight
// (retrieval or AI generation) — the elapsed-time counter and bouncing dots
// Gradio's own chatbot used to show for free while a response was pending.
export function TypingIndicator() {
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
        <span className="typing-dots" aria-hidden="true">
          <span className="typing-dot" />
          <span className="typing-dot" />
          <span className="typing-dot" />
        </span>
        <span className="typing-elapsed">Timp scurs: {elapsedSeconds}s</span>
      </div>
    </div>
  );
}
