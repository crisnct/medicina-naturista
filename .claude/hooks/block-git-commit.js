#!/usr/bin/env node
// PreToolUse(Bash) guard: refuse any command that would create a commit or
// publish history. Committing in this repository is the user's decision, not
// the agent's — see .claude/hooks/README.md.
//
// Exit 0 = allow, exit 2 = block (stderr is shown to the model).

"use strict";

function check(raw) {
  let command = "";
  try {
    const payload = JSON.parse(raw || "{}");
    command = payload?.tool_input?.command ?? payload?.tool_input?.cmd ??
      payload?.command ?? payload?.cmd ?? "";
  } catch {
    // Unparsable payload: do not block on a guard bug.
    process.exit(0);
  }
  if (typeof command !== "string" || !command.trim()) process.exit(0);

  const hit = findBlocked(command);
  if (!hit) process.exit(0);

  process.stderr.write(
    `BLOCKED: "${hit.label}" is not permitted — committing and publishing history ` +
      `in this repository is the user's decision.\n\n` +
      `Do the work in the working tree and stop there. Report what changed and let the ` +
      `user review and commit it themselves. If they have explicitly asked you to commit ` +
      `in this conversation, tell them this hook blocks it and that they can remove the ` +
      `PreToolUse entry in .claude/settings.json or run the command themselves.\n`,
  );
  process.exit(2);
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
    if (match) return { label: match[1] };
  }
  return null;
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
