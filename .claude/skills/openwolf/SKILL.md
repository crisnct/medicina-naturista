---
name: openwolf
description: OpenWolf operating protocol for this project. Load when starting multi-file work, resuming a session, wrapping up a session, or when unsure how to use .wolf/ state files (anatomy, cerebrum, memory, buglog, STATUS).
---

# OpenWolf Operating Protocol

Read repository-root `AGENTS.md` and `.claude/README.md` for the shared contract and host
compatibility. This protocol applies to Claude and ChatGPT/Codex. Bookkeeping is automatic
only when OpenWolf hooks are installed in the current host. Claude's `.claude/settings.json`
does not establish that for Codex. Never manually update `.wolf/anatomy.md`; use the CLI
when available. Memory writes require authorization under the current session's rules.

## Session resume

`.wolf/STATUS.md` is the handoff document. Read it first when resuming; it replaces re-reading memory, plans, and code to reconstruct context. Regenerate it on demand with `/handoff` when a quest finishes or before suggesting `/clear`.

## File navigation

1. To locate a symbol or file by name, run `openwolf find <query>` first: a ranked shortlist from the index (~1k tokens max), cheaper than grepping the world. For one file's description, size, and symbol line ranges: `openwolf find --file <path>`.
2. If the description answers your question, skip the full read. For large files, use targeted reads with line ranges. Installed pre-read hooks can surface sections, and `openwolf map` prints a token-budgeted overview.
3. Never read `.wolf/anatomy.md` whole; it is an index. Grep it only for a single path's line when `find` is unavailable.
4. If a file is not indexed or the CLI is unavailable, use `rg` and `rg --files` through
   the available file or terminal tools. Refresh with `openwolf scan` only when installed.

## Code generation and learning

1. Before generating code, check `.wolf/cerebrum.md`: respect `## Do-Not-Repeat` (past mistakes), `## Key Learnings`, and `## User Preferences`.
2. When memory writes are authorized, record user corrections and reusable project facts
   in cerebrum.md. Do not treat this protocol as permission to override memory restrictions.

## Bug logging

Before fixing any bug: grep `.wolf/buglog.json` for the error message or filename; the fix may already be known.

After fixing any bug, failed test, failed build, or user-reported problem: append an entry with `id`, `timestamp`, `error_message`, `file`, `root_cause`, `fix`, `tags`, `occurrences`, `last_seen`. Also log when you edit a file more than twice to get it right.

## Token discipline

- Never re-read a file already read this session unless it changed since.
- Prefer anatomy descriptions and targeted Grep over full file reads.
- If appending to a file, do not read the entire file first.

## Session end

When handoff is requested, follow `.claude/commands/handoff.md`: Claude may use `/handoff`,
while ChatGPT/Codex may invoke the handoff skill or read the workflow directly. Preserve
unfinished work. Write session memory or learnings only when authorized; never invent
hook-maintained entries, session IDs or successful runs.

## On-demand skills

- `/handoff`: regenerate .wolf/STATUS.md from the session's actual state.
- `/designqc`: screenshot-based design review of the running app.
- `/reframe`: UI framework selection, migration, and anti-generic design audits.
- `/security-audit`: security review of the project.
