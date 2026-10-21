# Project hooks

Hooks owned by this repository, registered for Claude in `.claude/settings.json` and for
Codex in `.codex/hooks.json`. The hooks under
`.wolf/hooks/` belong to OpenWolf and are maintained separately — do not edit those here.

## ChatGPT/Codex and manual use

Read repository-root `AGENTS.md` and `.claude/README.md`. These scripts work with Node
from any assistant's terminal, but `.claude/settings.json` registers them only in Claude.
Both configurations register the OpenWolf adapter and the no-commit guard. The adapter
runs the Ruff check after each written file. A regex command check is advisory
outside its registered host; it is not an OS security boundary.

From the repository root, in PowerShell or Bash:

```text
node .claude/hooks/block-git-commit.js --command "git status --short"
node .claude/hooks/ruff-format-check.js --file src/backend/config.py
```

The first command only checks the supplied command; it never executes Git. To verify
blocking, supply `--command "git commit -m example"` and expect exit code 2. The file
check runs Ruff without modifying the file. Both hooks retain Claude's JSON stdin
contract; they also accept top-level `command`/`cmd` or `file_path` payloads for manual
adapters. Codex patch translation is handled by `openwolf-compat.js`.

## OpenWolf compatibility

`openwolf-compat.js claude|codex <hook-name>` forwards native lifecycle events to
OpenWolf and sets agent attribution explicitly. Claude's file payloads pass through;
Codex `apply_patch` payloads are split into individual create, edit, move and delete
observations. Each file gets its own event identifier derived from the tool call.
Deletions remove stale anatomy entries using OpenWolf's locked store API. The adapter
does not change OpenWolf's generated scripts or reconstruct historical empty sessions.

The Bash hook also registers literal, single-file PowerShell `Get-Content` reads.
Compound commands, globs and arbitrary shell writes are not interpreted as file events.
Keep file edits in the host's dedicated edit tool for complete write bookkeeping.

Both hosts share `.wolf/memory.md` and anatomy, while session state and usage attribution
remain separate. A shared project journal does not synchronize the hosts' chat histories.
Local command hooks require a host that supports them; cloud-orchestrated Work does not
execute these local registrations.

After initializing or updating OpenWolf, restore the repository registrations with:

```text
node .claude/hooks/setup-openwolf-hooks.js --apply
node .claude/hooks/setup-openwolf-hooks.js --check
```

The setup script preserves unrelated hooks and settings. Reload the sessions after
configuration changes. Codex may require trust of changed hook definitions; approval
belongs to the user and is not bypassed by these scripts. Run `openwolf.cmd status` and
inspect new journal entries after real file edits. Initialization alone is not evidence
that writes are being tracked.

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

**Event:** `PostToolUse`, called by `openwolf-compat.js` after OpenWolf's
`post-write.js` for each written file, in both hosts.

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
