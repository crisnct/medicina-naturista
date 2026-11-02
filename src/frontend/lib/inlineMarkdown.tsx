import type { ReactNode } from "react";

// Renders the very small Markdown subset _recommendation_text() produces
// (**bold** spans, level-three headings, line breaks) as plain React elements — never
// dangerouslySetInnerHTML, so there is no HTML-injection surface at all,
// unlike the Gradio version's raw HTML string building.
export function renderRecommendationText(content: string): ReactNode {
  const lines = content.split("\n");
  // Lines between a heading and the first numbered entry are explanatory notes.
  let intro = false;
  return lines.map((line, lineIndex) => {
    const heading = line.match(/^###\s+(.+)$/);
    if (heading) {
      intro = true;
      return <h3 key={lineIndex} className="message-heading">{renderInlineBold(heading[1])}</h3>;
    }
    if (/^\d+\.\s/.test(line)) intro = false;
    const blank = line.trim() === "";
    return (
      <p key={lineIndex} className={blank ? "message-line-spacer" : intro ? "message-line message-note" : "message-line"}>
        {renderInlineBold(line)}
      </p>
    );
  });
}

function renderInlineBold(line: string): ReactNode[] {
  const parts = line.split(/\*\*(.+?)\*\*/g);
  return parts.map((part, index) => (index % 2 === 1 ? <strong key={index}>{part}</strong> : part));
}
