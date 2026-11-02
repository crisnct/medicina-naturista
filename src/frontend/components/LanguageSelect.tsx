import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import type { Language } from "../lib/texts";

const OPTIONS: { value: Language; name: string }[] = [
  { value: "ro", name: "Română" },
  { value: "en", name: "English" },
];

// Flags are drawn, not emoji: Windows has no flag emoji, and a native <select> cannot show images.
function Flag({ language }: { language: Language }) {
  const id = useId().replaceAll(":", "");
  return (
    <svg className="language-flag" viewBox="0 0 60 40" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      {language === "ro" ? (
        <>
          <rect width="20" height="40" fill="#002b7f" />
          <rect x="20" width="20" height="40" fill="#fcd116" />
          <rect x="40" width="20" height="40" fill="#ce1126" />
        </>
      ) : (
        <>
          <clipPath id={`${id}-frame`}><path d="M0 0h60v40H0z" /></clipPath>
          <clipPath id={`${id}-diagonals`}><path d="M30 20h30v20zM30 20v20H0zM30 20H0V0zM30 20V0h30z" /></clipPath>
          <g clipPath={`url(#${id}-frame)`}>
            <path d="M0 0h60v40H0z" fill="#012169" />
            <path d="M0 0l60 40M60 0L0 40" stroke="#fff" strokeWidth="8" />
            <path d="M0 0l60 40M60 0L0 40" clipPath={`url(#${id}-diagonals)`} stroke="#c8102e" strokeWidth="5" />
            <path d="M30 0v40M0 20h60" stroke="#fff" strokeWidth="13" />
            <path d="M30 0v40M0 20h60" stroke="#c8102e" strokeWidth="8" />
          </g>
        </>
      )}
    </svg>
  );
}

export function LanguageSelect({ value, labelId, disabled, onChange }: {
  value: Language;
  labelId: string;
  disabled?: boolean;
  onChange: (language: Language) => void;
}) {
  const listId = useId();
  const root = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const selectedIndex = OPTIONS.findIndex((option) => option.value === value);
  const current = OPTIONS[selectedIndex] ?? OPTIONS[0];

  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  useEffect(() => { if (disabled) setOpen(false); }, [disabled]);

  const openList = () => { setActive(Math.max(selectedIndex, 0)); setOpen(true); };
  const choose = (index: number) => {
    setOpen(false);
    if (OPTIONS[index].value !== value) onChange(OPTIONS[index].value);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (!open) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) { event.preventDefault(); openList(); }
      return;
    }
    switch (event.key) {
      case "ArrowDown": event.preventDefault(); setActive((index) => Math.min(index + 1, OPTIONS.length - 1)); break;
      case "ArrowUp": event.preventDefault(); setActive((index) => Math.max(index - 1, 0)); break;
      case "Home": event.preventDefault(); setActive(0); break;
      case "End": event.preventDefault(); setActive(OPTIONS.length - 1); break;
      case "Enter": case " ": event.preventDefault(); choose(active); break;
      case "Escape": event.preventDefault(); setOpen(false); break;
      case "Tab": setOpen(false); break;
    }
  };

  return (
    <div className="language-select" ref={root}>
      <button
        type="button"
        id="application-language"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-labelledby={labelId}
        aria-activedescendant={open ? `${listId}-${active}` : undefined}
        disabled={disabled}
        onClick={() => (open ? setOpen(false) : openList())}
        onKeyDown={onKeyDown}
      >
        <Flag language={current.value} />
        <span>{current.name}</span>
        <svg className="language-chevron" viewBox="0 0 12 12" aria-hidden="true">
          <path d="m2.5 4.5 3.5 3.5 3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <ul id={listId} role="listbox" aria-labelledby={labelId}>
          {OPTIONS.map((option, index) => (
            <li
              key={option.value}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={option.value === value}
              className={index === active ? "active" : undefined}
              onMouseEnter={() => setActive(index)}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => choose(index)}
            >
              <Flag language={option.value} />
              <span>{option.name}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
