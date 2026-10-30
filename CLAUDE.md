# Claude Code entry point

Read and follow [AGENTS.md](AGENTS.md) before working in this repository. It is the
shared project contract for Claude Code and ChatGPT/Codex: what the app is (a bilingual
RO/EN naturopathy assistant with a local hybrid-retrieval index), the layout, the commands
for tests and CI, the conventions and the invariants that must not be broken.

Read [.claude/README.md](.claude/README.md) for workflow discovery and host differences.
Claude-specific hooks remain registered in `.claude/settings.json`; reusable role
guides and commands remain under `.claude/` and are exposed to Codex through
`.agents/skills/`. Keep project-wide instructions in `AGENTS.md` to avoid drift.

Claude-enforced policies, in short (details in `AGENTS.md` and `.claude/hooks/README.md`):

- Never commit or push; `.claude/hooks/block-git-commit.js` refuses it. The user commits.
- Ruff runs after every written `.py` file under `src/`; fix failures before continuing.
- Existing tests may be modified and run; do not add test files or test cases.
- Commands need `PYTHONPATH=src` and the project interpreter `.venv/Scripts/python.exe`.

# OpenWolf

This project uses OpenWolf for context management. The always-on rules live in `.claude/rules/openwolf.md`; the hooks handle bookkeeping (anatomy index, memory log, read tracking) automatically.

For the full operating protocol (session handoff, memory discipline, bug logging), load the `openwolf` skill, or read `.wolf/OPENWOLF.md`. Regenerate the session handoff with `/handoff`.
