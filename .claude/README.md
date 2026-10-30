# Shared assistant instructions

This directory contains project guidance shared by Claude Code and ChatGPT/Codex,
alongside Claude-specific configuration. The repository contract is [AGENTS.md](../AGENTS.md).
[CLAUDE.md](../CLAUDE.md) points Claude to the same contract.

## Entry points

| Capability | Shared source | Codex discovery |
|---|---|---|
| Engineering role guides | `skills/medicina-engineering/` | `.agents/skills/medicina-engineering/SKILL.md` |
| OpenWolf protocol | `skills/openwolf/SKILL.md`, `rules/openwolf.md` | `.agents/skills/openwolf/SKILL.md` |
| Testing role | `agents/app-tester.md` | `.agents/skills/app-tester/SKILL.md` |
| Session handoff | `commands/handoff.md` | `.agents/skills/handoff/SKILL.md` |
| Visual review | `commands/designqc.md` | `.agents/skills/designqc/SKILL.md` |
| UI framework/design work | `commands/reframe.md` | `.agents/skills/reframe/SKILL.md` |
| Security audit | `commands/security-audit.md` | `.agents/skills/security-audit/SKILL.md` |

Paths in the table are relative to this directory, except `.agents/`, which is at
the repository root. The Codex skills are thin adapters to these maintained sources;
change the shared source rather than copying the full instructions into each adapter.

Claude can use its existing slash commands and agent. In Codex, select the corresponding
skill or request the workflow in ordinary language. In ChatGPT sessions without local
workspace access, provide the relevant files; local discovery and commands require tools
with access to this checkout. Do not claim instructions were loaded without reading them.

## Directory contents

| Path | Purpose |
|---|---|
| `agents/app-tester.md` | Testing role (Claude subagent; plain instructions for other hosts) |
| `commands/` | Slash commands: `handoff`, `designqc`, `reframe`, `security-audit` |
| `skills/medicina-engineering/` | Role guides: Python development/review, architecture, XMind, draw.io, database, embeddings, Docker/CI |
| `skills/openwolf/`, `rules/openwolf.md` | OpenWolf protocol and always-on rules |
| `hooks/` | Repository-owned hooks: no-commit guard, Ruff check, OpenWolf adapter (see `hooks/README.md`) |
| `settings.json` | Claude hook registrations and the OpenWolf status line |
| `launch.json` | Preview servers: `naturist-app` (Uvicorn, port 7861) and `naturist-frontend` (Vite, port 5173) |

The application is bilingual (Romanian default, English): keep user-facing copy in
`src/backend/resources/texts.{ro,en}.toml` and prompts in `ai/prompts/` and `ai/prompts/en/`.
Role guides here describe the conventions; `AGENTS.md` and `README.md` remain authoritative.

## Tool and shell compatibility

The task instructions apply regardless of assistant; tool names describe capabilities:

| Claude term | Other assistants |
|---|---|
| `Bash` | Available terminal/shell tool; this Windows workspace commonly uses PowerShell |
| `Read`, `Glob`, `Grep` | Available file tools, `rg --files`, `rg`, targeted file reads |
| `Write`, `Edit`, `MultiEdit` | Available patch/file editing tools |
| `WebFetch` | Available browser or web retrieval tool, when the task permits internet access |
| `Read` on a screenshot | Available local image viewer |
| `$ARGUMENTS` | The arguments or scope supplied by the user for this workflow |

Adapt shell syntax to the active shell. For example, Bash's `PYTHONPATH=src command`
becomes `$env:PYTHONPATH = 'src'` followed by the command in PowerShell. Invoke the
project interpreter as `.venv/Scripts/python.exe` on Windows and `.venv/bin/python`
on Linux. Do not infer installed tools, model availability, delegation, or authorization
from Claude-specific frontmatter (`tools`, `model`, `argument-hint`, `globs`). Follow
the testing role directly when delegation is unavailable or unauthorized.

## Runtime-specific files

`settings.json` and `launch.json` are Claude configuration; do not copy their schema into
Codex configuration. Codex registrations live separately in `.codex/hooks.json`, with
hooks enabled in `.codex/config.toml`. Both hosts use the repository-owned
`hooks/openwolf-compat.js` adapter; see [hook setup](hooks/README.md#openwolf-compatibility)
for verification and re-registration after an OpenWolf update.
Other assistants follow the same no-commit policy and run Ruff explicitly; the hook
scripts also accept manual CLI arguments documented in [hooks/README.md](hooks/README.md).

OpenWolf bookkeeping is automatic only where hooks have actually been installed.
If its CLI is unavailable, use targeted file searches and report the missing bookkeeping
capability. Do not install it, invent session IDs, or fabricate hook events as a fallback.
Existing user restrictions on memory writes apply to `.wolf` files as well.

## Discovery verification

Check that `AGENTS.md` and all seven `.agents/skills/*/SKILL.md` adapters exist and their
source links resolve. Validate each skill with the installed skill-creator validator
when available. A host's skill picker is the final check of runtime discovery; refresh
or restart the session if its instruction inventory is stale. These repository files
do not modify global ChatGPT/Codex settings or install a plugin.

Official references: [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
and [local skills](https://learn.chatgpt.com/docs/build-skills).
