#!/usr/bin/env node
// PreToolUse(Bash) guard: refuse any command that would create a commit or
// publish history, except `git commit` and a non-destructive `git push` made
// from the agent's own `claude/*` work branch. Anything that touches another
// branch stays the user's decision — see .claude/hooks/README.md.
//
// Exit 0 = allow, exit 2 = block (stderr is shown to the model).

"use strict";

const { execFileSync } = require("node:child_process");

function check(raw) {
  let command = "";
  let cwd = process.cwd();
  try {
    const payload = JSON.parse(raw || "{}");
    command = payload?.tool_input?.command ?? payload?.tool_input?.cmd ??
      payload?.command ?? payload?.cmd ?? "";
    if (typeof payload?.cwd === "string" && payload.cwd) cwd = payload.cwd;
  } catch {
    // Unparsable payload: do not block on a guard bug.
    process.exit(0);
  }
  if (typeof command !== "string" || !command.trim()) process.exit(0);

  // Every blocked verb in a chain must be allowed; one bad segment blocks the whole command.
  const hits = findBlocked(command);
  if (hits.length === 0) process.exit(0);
  const hit = hits.find((candidate) => !allowedOnAgentBranch(candidate, command, cwd));
  if (!hit) process.exit(0);

  process.stderr.write(
    `BLOCKED: "${hit.label}" is not permitted here — committing and publishing history ` +
      `outside a claude/* work branch is the user's decision.\n\n` +
      `Do the work in the working tree and stop there. Report what changed and let the ` +
      `user review and commit it themselves. If they have explicitly asked you to commit ` +
      `in this conversation, switch to a claude/* branch (commit and a plain push are ` +
      `allowed there), or tell them they can remove the PreToolUse entry in ` +
      `.claude/settings.json or run the command themselves.\n`,
  );
  process.exit(2);
}

// The agent's own work branches; the only place commit and push are allowed.
const AGENT_BRANCH = /^claude\//;
const AGENT_REF = /^(?:refs\/heads\/)?claude\//;

// A push may only publish the agent branch, and never rewrite, delete or mass-publish.
function safePush(args) {
  const positional = [];
  for (const arg of args) {
    if (["--force", "--delete", "--mirror", "--all", "--tags", "--prune", "--no-verify"].includes(arg)) {
      return false;
    }
    if (/^-[a-zA-Z]*[fd][a-zA-Z]*$/.test(arg)) return false;
    if (arg.startsWith("-")) continue;
    positional.push(arg);
  }
  // positional[0] is the remote; the rest are refspecs, where `+` forces and `:dst` names the target.
  return positional.slice(1).every((spec) => {
    if (spec.startsWith("+")) return false;
    const target = spec.includes(":") ? spec.slice(spec.lastIndexOf(":") + 1) : spec;
    return target === "HEAD" || AGENT_REF.test(target);
  });
}

function allowedOnAgentBranch(hit, command, cwd) {
  if (hit.verb !== "commit" && hit.verb !== "push") return false;
  // -C / -c / --git-dir can aim the command at a repository or branch other than the one checked below.
  if (hit.hasGlobalOptions) return false;
  if (hit.args.includes("--no-verify")) return false;
  // The branch is read before the command runs, so a chained checkout would invalidate it.
  if (/\bgit\b[^;&|\n]*\b(checkout|switch|reset)\b/.test(command)) return false;
  if (hit.verb === "push" && !safePush(hit.args)) return false;
  try {
    const branch = execFileSync("git", ["rev-parse", "--abbrev-ref", "HEAD"], {
      cwd,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
    return AGENT_BRANCH.test(branch);
  } catch {
    // Cannot prove the branch: keep the block.
    return false;
  }
}

// Commands that create commits or publish them. Matched as `git <verb>`, with
// any `git` global options (-C <path>, -c k=v, --git-dir=...) in between.
const BLOCKED_VERBS = [
  ["commit", "git commit"],
  ["merge", "git merge (creates a merge commit)"],
  ["revert", "git revert (creates a commit)"],
  ["cherry-pick", "git cherry-pick (creates a commit)"],
  ["am", "git am (creates commits)"],
  ["rebase", "git rebase (rewrites commits)"],
  ["push", "git push (publishes history)"],
];

function findBlocked(command) {
  // Split on separators so `foo && git commit -m x` is caught, and strip
  // single/double quoted spans so a quoted "git commit" in a message is not.
  const unquoted = command
    .replace(/'[^']*'/g, " ")
    .replace(/"[^"]*"/g, " ");

  for (const segment of unquoted.split(/\|\||&&|[;|&\n]/)) {
    const words = segment.trim().split(/\s+/).filter(Boolean);
    const start = words.findIndex((w) => w === "git" || w.endsWith("/git"));
    if (start === -1) continue;

    // Walk past git's own options to reach the subcommand.
    let i = start + 1;
    while (i < words.length) {
      const w = words[i];
      if (w === "-C" || w === "-c") i += 2;
      else if (w.startsWith("-")) i += 1;
      else break;
    }
    const verb = words[i];
    if (!verb) continue;

    const match = BLOCKED_VERBS.find(([v]) => v === verb);
    if (match) {
      hits.push({
        label: match[1],
        verb,
        args: words.slice(i + 1),
        hasGlobalOptions: i > start + 1,
      });
    }
  }
  return hits;
}

// Keep Claude's JSON stdin contract; other hosts can check an explicit command.
if (process.argv[2] === "--command" && process.argv[3]) {
  check(JSON.stringify({ command: process.argv[3] }));
} else {
  let raw = "";
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", (chunk) => (raw += chunk));
  process.stdin.on("end", () => check(raw));
}
