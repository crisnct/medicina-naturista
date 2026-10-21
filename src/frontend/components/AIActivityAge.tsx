import { tr } from "../lib/texts";
import { useEffect, useState } from "react";

export function AIActivityAge({ ageMs, receivedAt }: { ageMs: number; receivedAt: number }) {
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    setNow(performance.now());
    const interval = window.setInterval(() => setNow(performance.now()), 1000);
    return () => window.clearInterval(interval);
  }, [ageMs, receivedAt]);

  const seconds = Math.floor((Math.max(0, ageMs) + Math.max(0, now - receivedAt)) / 1000);
  const formatted = `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}`;
  return <span className="ai-activity-age" aria-live="off">{tr("interface.activity_age", { duration: formatted })}</span>;
}
