# Project hooks

Hooks owned by this repository, registered in `.claude/settings.json`. The hooks under
`.wolf/hooks/` belong to OpenWolf and are maintained separately — do not edit those here.

## `block-git-commit.js`

**Event:** `PreToolUse`, matcher `Bash`. Registered *before* the OpenWolf `pre-bash.js`
hook so a blocked command never reaches it.

Refuses any Bash command that would create a commit or publish history:
`git commit`, `merge`, `revert`, `cherry-pick`, `am`, `rebase`, `push`. Exit code 2
blocks the tool call and shows the agent the reason.

**Rationale.** Committing is a judgement call about what belongs in the project's
history, and it is the user's to make. The agent does the work in the working tree and
stops; the user reviews `git status`/`git diff` and commits.

**Still allowed:** everything read-only or local-only — `status`, `diff`, `log`, `show`,
`add`, `stash`, `branch`, `checkout`. Staging is permitted so an agent can still prepare
a change set for review.

**Matching.** Quoted spans are stripped before matching, so `echo "git commit ..."` is
not blocked. Chained commands are split on `&&`, `||`, `;`, `|` and newlines, so
`npm test && git commit -m x` is caught. Git global options are skipped, so
`git -C /path commit` is caught too.

**Escape hatch.** The user can run the command themselves, or remove this entry from the
`PreToolUse` → `Bash` array in `.claude/settings.json`. The agent must not work around
it — not by `.git/hooks`, not by a wrapper script, not by asking another session to run
the command.

Self-test:

```bash
echo '{"tool_input":{"command":"git commit -m x"}}' | node .claude/hooks/block-git-commit.js; echo "exit=$?"
```

Expect `exit=2` with an explanation on stderr; `git status` should give `exit=0` and no
output.

## `ruff-format-check.js`

**Event:** `PostToolUse`, matcher `Write|Edit|MultiEdit`. Registered *after* the OpenWolf
`post-write.js` hook so the anatomy index is updated either way.

After a `.py` file under `src/` is written, runs `ruff format --check` and `ruff check`
on that one file — the two gates the CI `static` job applies to the whole tree. Exit 2
reports the failure and the fix commands, so a formatting-only CI red is caught
immediately instead of after a push.

**Scope.** Only `.py` files under `src/`, excluding `src/scripts/dictionaires/`
(vendored Hunspell) and `src/scripts/icd10_work/` (one-off scripts) — matching
`extend-exclude` in `pyproject.toml`. Everything else exits silently.

**Degrades silently.** If ruff is not installed, the file is gone, the payload is
malformed, or the hook itself errors, it exits 0 and says nothing. A missing dev
environment must not nag on every edit. It looks for ruff in this order:
`.venv/Scripts/ruff.exe`, `.venv/bin/ruff`, `.venv/…/python -m ruff`, then PATH.

Note for anyone editing it: Node's `execFileSync` cannot resolve a Windows `.cmd`/`.bat`
shim (it fails `EINVAL`), so PATH lookup goes through `python -m ruff` rather than a bare
`ruff`. Don't "simplify" that back.

**Advisory, not a gate.** It reports after the write; the file is already on disk. It
tells the agent to fix the formatting, it does not revert anything.

Self-test — with ruff installed, write a badly formatted file under `src/` and expect
`exit=2`:

```bash
echo '{"tool_input":{"file_path":"'$PWD'/src/backend/config.py"}}' | node .claude/hooks/ruff-format-check.js; echo "exit=$?"
```
