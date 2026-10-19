---
description: OpenWolf protocol enforcement, active on all files
globs: **/*
---

- Applies to Claude and ChatGPT/Codex through repository-root AGENTS.md. Claude-only frontmatter does not configure other hosts; see .claude/README.md.
- To locate a symbol or file, use `openwolf find <name>` when installed (ranked shortlist, under 1k tokens). Otherwise use `rg` and `rg --files`. For symbol ranges: `openwolf find --file <path>`. Never read .wolf/anatomy.md whole; it is an index.
- Check .wolf/cerebrum.md Do-Not-Repeat list before generating code (search "## Do-Not-Repeat"); record corrections only when memory writes are authorized.
- Do NOT manually update .wolf/anatomy.md or .wolf/memory.md; the OpenWolf hooks maintain them.
- BEFORE fixing any bug: run `openwolf bug search "<error>"` or grep .wolf/buglog.json. AFTER fixing one: log it there (error_message, root_cause, fix, tags).
- When resuming a session, read .wolf/STATUS.md first and verify it against current files. For a requested handoff use /handoff in Claude or the handoff skill/workflow in ChatGPT/Codex.
