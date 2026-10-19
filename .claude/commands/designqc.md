---
description: Screenshot-based design review of the running app via openwolf designqc
argument-hint: [--url <url>] [--routes <routes>]
---

Arguments: $ARGUMENTS (Claude), or the user's requested scope in ChatGPT/Codex.

Read repository-root `AGENTS.md` and `.claude/README.md`. This workflow uses the available
shell and local image viewer; it does not require Claude-specific tool names. If OpenWolf
is unavailable, inspect the running app using the host's supported browser tools and
report any capture limitation. Do not start unrelated servers or install tooling implicitly.

Evaluate and improve the design/UI of this app:

1. Run `openwolf designqc` via the available shell to capture screenshots (pass through the supplied arguments).
   - The command auto-detects a running dev server, or starts one from package.json if needed.
   - Use `--url <url>` only if auto-detection fails.
   - Compressed JPEG screenshots land in `.wolf/designqc-captures/`; full pages are captured as sectioned viewport-height images (top, section2, ..., bottom).
2. Inspect the captured screenshots from `.wolf/designqc-captures/` with the available local image viewer.
3. Evaluate against modern standards (Shadcn UI, Tailwind, clean React patterns):
   - Spacing and whitespace consistency
   - Typography hierarchy and readability
   - Color contrast and accessibility (WCAG)
   - Visual hierarchy and focal points
   - Component consistency
   - Whether the design looks generic ("white-coded", no personality)
4. Provide specific, actionable feedback with fix suggestions.
5. If the user approves, implement the fixes directly in their code.
6. Re-run `openwolf designqc` to verify the improvement.

Token awareness: each screenshot costs about 2,500 tokens. For large apps, use `--routes / /specific-page` to limit captures.
