#!/usr/bin/env node
// Reapply repository-owned adapters after OpenWolf regenerates harness registrations.
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "../..").split(path.sep).join("/");
const mode = process.argv[2] || "--check";
if (!["--check", "--apply"].includes(mode)) {
  console.error("Usage: setup-openwolf-hooks.js --check|--apply");
  process.exit(1);
}

try {
  const pending = [];
  for (const [file, agent] of [[".claude/settings.json", "claude"], [".codex/hooks.json", "codex"]]) {
    const target = path.join(root, file);
    const original = fs.readFileSync(target, "utf8");
    const settings = JSON.parse(original);
    let changed = false;
    for (const groups of Object.values(settings.hooks || {})) {
      for (const group of groups) {
        for (const hook of group.hooks || []) {
          const command = (hook.command || "").replaceAll("\\", "/");
          const native = command.match(/\/\.wolf\/hooks\/([\w-]+)\.js"?$/);
          const adapter = command.match(/openwolf-compat\.js"?\s+(?:claude|codex)\s+([\w-]+)$/);
          const name = native?.[1] || adapter?.[1];
          if (!name) continue;
          const script = path.join(root, ".wolf/hooks", `${name}.js`);
          if (!fs.existsSync(script)) throw new Error(`Missing OpenWolf hook: ${script}`);
          const desired = `node "${root}/.claude/hooks/openwolf-compat.js" ${agent} ${name}`;
          if (hook.command !== desired) { hook.command = desired; changed = true; }
          if (["pre-write", "post-write"].includes(name) && hook.timeout !== 60) {
            hook.timeout = 60;
            changed = true;
          }
        }
      }
    }
    const shell = settings.hooks?.PreToolUse?.find((group) => group.matcher === "Bash");
    if (!shell) throw new Error(`Missing Bash hook registration in ${file}; initialize OpenWolf first`);
    if (!shell.hooks.some((hook) => hook.command?.includes("block-git-commit.js"))) {
      shell.hooks.unshift({type: "command", command: `node "${root}/.claude/hooks/block-git-commit.js"`, timeout: 5});
      changed = true;
    }
    // Ruff runs inside the adapter for each affected file, including compound patches.
    for (const group of settings.hooks.PostToolUse || []) {
      const kept = group.hooks.filter((hook) => !hook.command?.includes("ruff-format-check.js"));
      if (kept.length !== group.hooks.length) { group.hooks = kept; changed = true; }
    }
    if (changed) pending.push({target, file, settings});
  }
  for (const {target, file, settings} of pending) {
    if (mode === "--apply") fs.writeFileSync(target, JSON.stringify(settings, null, 2) + "\n");
    console.log(`${mode === "--apply" ? "Updated" : "Needs update"}: ${file}`);
  }
  if (!pending.length) console.log("OpenWolf adapters registered for Claude and Codex.");
  if (pending.length && mode === "--check") process.exitCode = 1;
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
