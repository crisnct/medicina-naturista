import type { ReactNode } from "react";

// Renders the very small Markdown subset _recommendation_text() produces
// (**bold** spans, line breaks) as plain React elements — never
// dangerouslySetInnerHTML, so there is no HTML-injection surface at all,
// unlike the Gradio version's raw HTML string building.
export function renderRecommendationText(content: string): ReactNode {
  const lines = content.split("\n");
  return lines.map((line, lineIndex) => (
    <p key={lineIndex} className={line.trim() === "" ? "message-line-spacer" : "message-line"}>
      {renderInlineBold(line)}
    </p>
  ));
}

function renderInlineBold(line: string): ReactNode[] {
  const parts = line.split(/\*\*(.+?)\*\*/g);
  return parts.map((part, index) => (index % 2 === 1 ? <strong key={index}>{part}</strong> : part));
}
