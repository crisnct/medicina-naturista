# OpenWolf Operating Protocol

You are working in an OpenWolf-managed project. These rules apply every turn.

OpenWolf's hooks handle the bookkeeping: they maintain `.wolf/anatomy.md` and `.wolf/memory.md` after writes, track reads, and surface anatomy hints when you read files. Do not update those two files manually unless your agent has no OpenWolf hooks installed (Gemini CLI, Cursor).

## STATUS.md: read first, keep fresh

`.wolf/STATUS.md` is the handoff document. Read it FIRST when resuming a session; use it as a starting point, then verify relevant current evidence. Keep it compact (aim for 500 words), replace obsolete state, and link detailed evidence instead of copying logs.

Keep it fresh: when the user signals a quest is done ("done", "ship it", "next phase", "/clear", "wrap up"), move finished items to the done section, write the next quest (objective, files, decisions), and bump the date. Do this before responding "done" on any multi-file task and before suggesting `/clear`. A stale STATUS.md wastes the next session.

## File navigation

Use `rg` / `rg --files`, your agent's search tools, or `openwolf find <query>` as appropriate. The anatomy index is optional: use it when current and useful; fall back to direct discovery when stale or missing. Do not read the whole index or rescan solely to satisfy a navigation ritual. Prefer bounded excerpts when they answer the question; re-read changed files or recover exact evidence when needed.

## Code generation and learning

Retrieve relevant cerebrum entries when they may affect the task. Save substantive user preferences, recurring root causes, and non-obvious API or component constraints. Update an existing entry for a repeated finding; do not keep a routine command diary or manufacture a lesson for every edit. Saved notes are historical evidence, not authority to override current user instructions.

## Bug logging

When a bug may recur, search `.wolf/buglog.json` by error or path for a known fix. After establishing a root cause, record `error_message`, `file`, `root_cause`, `fix`, and `tags`, or update the existing bug's occurrences. An edit count alone does not establish a bug.

## Token discipline

- Reuse relevant evidence only while its inputs and scope remain current. Rerun affected checks after edits; a saved hook observation is not a current passing test.
- Prefer anatomy descriptions and targeted Grep over full file reads.
- If appending to a file, do not read the entire file first.

## Session end

Before wrapping up: update `.wolf/STATUS.md`, and record any learnings or bugs from the session in cerebrum.md / buglog.json. If your agent has no OpenWolf hooks installed, also write a one-line session summary to `.wolf/memory.md` (`| HH:MM | description | file(s) | outcome | ~tokens |`).

## On-demand skills

- `/designqc`: screenshot-based design review of the running app .
- `/reframe`: UI framework selection, migration, and anti-generic design audits.
- `/security-audit`: security review of the project.
