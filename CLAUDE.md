# OpenWolf

This project uses OpenWolf for context management. The always-on rules live in `.claude/rules/openwolf.md`; the hooks handle bookkeeping (anatomy index, memory log, read tracking) automatically.

For the full operating protocol (session handoff, memory discipline, bug logging), load the `openwolf` skill, or read `.wolf/OPENWOLF.md`. Regenerate the session handoff with `/handoff`.


# Claude Code entry point

Read and follow [AGENTS.md](AGENTS.md) before working in this repository. It is the
shared project contract for Claude Code and ChatGPT/Codex.

Read [.claude/README.md](.claude/README.md) for workflow discovery and host differences.
Claude-specific hooks remain registered in `.claude/settings.json`; reusable role
guides and commands remain under `.claude/` and are exposed to Codex through
`.agents/skills/`. Keep project-wide instructions in `AGENTS.md` to avoid drift.
