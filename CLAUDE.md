# Claude Code entry point

Read and follow [AGENTS.md](AGENTS.md) before working in this repository. It is the
shared project contract for Claude Code and ChatGPT/Codex.

Read [.claude/README.md](.claude/README.md) for workflow discovery and host differences.
Claude-specific hooks remain registered in `.claude/settings.json`; reusable role
guides and commands remain under `.claude/` and are exposed to Codex through
`.agents/skills/`. Keep project-wide instructions in `AGENTS.md` to avoid drift.
