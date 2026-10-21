# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-10-21T04:00:47.577Z
> Files: 32 tracked | Anatomy hits: 0 | Misses: 0

> Project structure index. Auto-maintained by OpenWolf hooks and daemon.
> Run `openwolf scan` to generate, or wait for the first Claude Code session.
> Status: Pending initial scan

## ./

- `docker-compose.yaml` — Docker Compose: 4 services (~1905 tok)
- `pyproject.toml` — " = ["E402"] (~629 tok)
- `README.md` — Project documentation (~23505 tok)

## .claude/agents/

- `app-tester.md` — Environment (~3390 tok)

## .claude/hooks/

- `block-git-commit.js` — PreToolUse(Bash) guard: refuse any command that would create a commit or (~785 tok)
- `README.md` — Project documentation (~855 tok)
- `ruff-format-check.js` — PostToolUse(Write|Edit|MultiEdit) advisory: after a .py file under src/ is (~1154 tok)

## .claude/skills/medicina-engineering/

- `architecture.md` — Senior architect — architecture documentation (~2136 tok)
- `database-engineering.md` — Senior Python developer — database expert (~2050 tok)
- `devops-docker-ci.md` — DevOps engineer — Docker, Compose, GitHub Actions (~1438 tok)
- `draw-io.md` — draw.io diagrams (~920 tok)
- `embeddings-engineering.md` — Senior Python developer — embeddings specialist (~2028 tok)
- `python-code-review.md` — Senior Python lead — code review (~1076 tok)
- `python-development.md` — Senior Python developer — general development (~3198 tok)
- `SKILL.md` — Engineering roles for medicina-naturista (~971 tok)
- `xmind-architecture.md` — Senior architect — the architecture diagrams (~849 tok)
- `xmind.md` — XMind 8 — file format and editing (~1060 tok)

## src/backend/core/

- `texts.py` — Validated Romanian copy; imports are inert and each process owns one immutable snapshot. (~867 tok)

## src/backend/integrations/

- `gmail.py` — Gmail API delivery for generated reports. (~2035 tok)

## src/backend/reporting/

- `pdf.py` — Readable Romanian PDF report with source references next to each claim. (~14459 tok)

## src/backend/resources/

- `texts.ro.toml` — Textele aplicației. Cheile și parametrii sunt în engleză; mesajele sunt în română. (~7216 tok)

## src/backend/web/

- `main.py` — FastAPI JSON boundary. Slow stages use independent snapshots and atomic commits. (~10879 tok)
- `texts.py` — Bootstrap public copy in the original Vite HTML; assets retain normal static serving. (~558 tok)

## src/frontend/

- `index.html` — __APP_TITLE__ (~135 tok)
- `main.tsx` — queryClient (~220 tok)
- `setupTests.ts` — Declares __APP_TEST_TEXTS__ (~148 tok)
- `styles.css` — Styles: 91 rules, 13 vars (~8591 tok)
- `vite.config.ts` — / <reference types="vitest/config" /> (~1158 tok)

## src/frontend/components/

- `FragmentsPanel.tsx` — CONDITION_OPTIONS (~3158 tok)
- `GeneratePanel.tsx` — Display names are editable; provider routing continues to use the original IDs. (~2894 tok)

## src/frontend/lib/

- `texts.ts` — Exports tr (~582 tok)

## src/scripts/

- `manage_texts.py` — Export public copy and regenerate key/parameter metadata, never a second editable catalog. (~783 tok)
