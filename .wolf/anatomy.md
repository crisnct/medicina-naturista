# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-10-17T07:50:07.944Z
> Files: 14 tracked | Anatomy hits: 0 | Misses: 0

> Project structure index. Auto-maintained by OpenWolf hooks and daemon.
> Run `openwolf scan` to generate, or wait for the first Claude Code session.
> Status: Pending initial scan

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
