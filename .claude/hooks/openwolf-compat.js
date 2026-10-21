#!/usr/bin/env node
// Keep harness translation outside OpenWolf's generated runtime, which updates overwrite.
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { pathToFileURL } = require("node:url");
const { randomUUID } = require("node:crypto");

const ROOT = path.resolve(__dirname, "../..");
const HOOKS = new Set([
  "session-start", "user-prompt-submit", "pre-read", "post-read", "pre-write",
  "post-write", "pre-bash", "post-bash", "post-batch", "precompact", "stop", "session-end",
]);

function patchFiles(command) {
  if (typeof command !== "string" || !command.startsWith("*** Begin Patch\n") &&
      !command.startsWith("*** Begin Patch\r\n")) return [];
  const files = [];
  let current;
  for (const line of command.split(/\r?\n/).slice(1)) {
    const header = line.match(/^\*\*\* (Add|Update|Delete) File: (.+)$/);
    if (header) {
      current = { kind: header[1], file: header[2], before: [], after: [] };
      files.push(current);
    } else if (current && line.startsWith("*** Move to: ")) {
      current.destination = line.slice("*** Move to: ".length);
    } else if (current && !line.startsWith("***") && !line.startsWith("@@")) {
      if (line.startsWith("-") || line.startsWith(" ")) current.before.push(line.slice(1));
      if (line.startsWith("+") || line.startsWith(" ")) current.after.push(line.slice(1));
    }
  }
  return files;
}

// Reject outside-project and secret paths before handing content to runtime indexers.
function projectFile(file, cwd) {
  const absolute = path.resolve(cwd, file);
  const relative = path.relative(ROOT, absolute);
  if (!relative || relative === ".." || relative.startsWith(`..${path.sep}`) ||
      path.isAbsolute(relative)) return null;
  return absolute;
}

function runHook(name, input) {
  const script = name === "ruff-format-check"
    ? path.join(__dirname, "ruff-format-check.js")
    : path.join(ROOT, ".wolf/hooks", `${name}.js`);
  const result = spawnSync(process.execPath, [script], {
    cwd: ROOT, env: process.env, input: JSON.stringify(input), encoding: "utf8",
    timeout: 12000, maxBuffer: 4 * 1024 * 1024, windowsHide: true,
  });
  if (result.stderr) process.stderr.write(result.stderr);
  if (result.error) throw result.error;
  if (result.status) process.exitCode = result.status;
  return result.stdout.trim();
}

// A compound patch can yield several advisory contexts; the host accepts one JSON object.
function emit(outputs) {
  const nonempty = outputs.filter(Boolean);
  if (!nonempty.length) return;
  if (nonempty.length === 1) {
    process.stdout.write(nonempty[0]);
    return;
  }
  const messages = nonempty.map((output) => JSON.parse(output));
  const result = {};
  const contexts = [];
  const systemMessages = [];
  for (const message of messages) {
    if (message.systemMessage) systemMessages.push(message.systemMessage);
    if (message.hookSpecificOutput) {
      const { additionalContext, ...fields } = message.hookSpecificOutput;
      result.hookSpecificOutput = { ...result.hookSpecificOutput, ...fields };
      if (additionalContext) contexts.push(additionalContext);
    }
    if (message.decision === "block") {
      result.decision = "block";
      result.reason = message.reason;
    }
  }
  if (contexts.length) result.hookSpecificOutput.additionalContext = contexts.join("\n");
  if (systemMessages.length) result.systemMessage = systemMessages.join("\n");
  process.stdout.write(JSON.stringify(result));
}

async function runtime(name) {
  return import(pathToFileURL(path.join(ROOT, ".wolf/hooks", `${name}.js`)).href);
}

// Native post-write assumes the file exists; deletions need removal, not an empty index entry.
async function deletedFile(input, file) {
  const shared = await runtime("shared");
  const relative = path.relative(ROOT, file).split(path.sep).join("/");
  if (relative.startsWith(".wolf/") || shared.isSensitiveFile(path.basename(file))) return;
  const storeApi = await runtime("anatomy-store");
  const locks = await runtime("anatomy-lock");
  const events = await runtime("event-journal");
  const wolfDir = path.join(ROOT, ".wolf");
  locks.withAnatomyLock(wolfDir, locks.HOOK_LOCK_BUDGET_MS, () => {
    const store = storeApi.loadStoreReconciled(wolfDir, ROOT);
    delete store.files[relative];
    storeApi.renderToFile(wolfDir, store);
    storeApi.saveStore(wolfDir, store);
  });
  const session = shared.getSessionFilePath(input);
  events.persistObservation(session, {
    id: input.tool_use_id, kind: "write", file: shared.normalizePath(file),
    action: "delete", tokens: 0, editKey: relative, at: new Date().toISOString(),
  });
  events.reconcileReads(session);
  shared.appendMarkdown(path.join(wolfDir, "memory.md"),
    `| ${shared.timeShort()} | Deleted ${relative.replaceAll("|", "\\|")} | — | ~0 |\n`);
}

function failed(response) {
  return response?.isError === true || response?.success === false ||
    typeof response?.exit_code === "number" && response.exit_code !== 0;
}

// Recognize only literal, single-file PowerShell reads; never infer reads from shell code.
function powershellRead(command, cwd) {
  if (typeof command !== "string") return null;
  const match = command.trim().match(
    /^(?:Get-Content|gc|cat)\s+(?:(?:-LiteralPath|-Path)\s+)?(?:'([^']+)'|"([^"$`]+)"|([^\s;'"|&<>$`*?]+))(?:\s+(-Raw)|\s+-(?:TotalCount|First|Head|Tail|Last)\s+\d+)?$/i,
  );
  if (!match) return null;
  const file = projectFile(match[1] || match[2] || match[3], cwd);
  return file ? { file_path: file, ...(/\s-(?:TotalCount|First|Head|Tail|Last)\s/i.test(command)
    ? { limit: 1 } : {}) } : null;
}

async function main(raw) {
  const [agent, hook] = process.argv.slice(2);
  if (!["claude", "codex"].includes(agent) || !HOOKS.has(hook)) {
    throw new Error("Usage: openwolf-compat.js claude|codex <hook-name>");
  }
  const input = JSON.parse(raw);
  if (JSON.parse(fs.readFileSync(path.join(ROOT, ".wolf/config.json"), "utf8"))
      .openwolf?.enabled === false) return;
  // Agent identity comes from registration, not inherited environment from the other app.
  for (const name of ["CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_PROJECT_DIR",
    "CODEX_PROJECT_ROOT", "CODEX_SANDBOX", "CODEX_THREAD_ID", "GROK_HOOK_EVENT",
    "GROK_SESSION_ID"]) delete process.env[name];
  process.env[agent === "claude" ? "CLAUDE_PROJECT_DIR" : "CODEX_PROJECT_ROOT"] = ROOT;
  process.env.OPENWOLF_PROJECT_ROOT = ROOT;
  const cwd = typeof input.cwd === "string" ? input.cwd : ROOT;
  const payload = { ...input, cwd: ROOT };
  const outputs = [];
  if (hook === "post-write" && failed(input.tool_response)) return;
  if (["pre-write", "post-write"].includes(hook) && input.tool_name === "apply_patch") {
    const changes = patchFiles(input.tool_input?.command);
    if (!changes.length) throw new Error("Unrecognized apply_patch payload; no writes recorded");
    for (const [index, change] of changes.entries()) {
      const file = projectFile(change.destination || change.file, cwd);
      const original = projectFile(change.file, cwd);
      if (!file || !original) continue;
      const normalized = {
        ...payload, tool_name: change.kind === "Add" ? "Write" : "Edit",
        // Keep the harness identity and give each file a distinct observation id.
        tool_use_id: `${input.tool_use_id || randomUUID()}:${index}`,
        tool_input: {
          file_path: file, old_string: change.before.join("\n"),
          new_string: change.after.join("\n"),
          ...(change.kind === "Add" ? { content: change.after.join("\n") } : {}),
        },
      };
      if (hook === "post-write" && change.kind === "Delete") {
        if (!fs.existsSync(original)) await deletedFile(normalized, original);
      } else if (hook === "pre-write" || fs.existsSync(file)) {
        outputs.push(runHook(hook, normalized));
        if (hook === "post-write") {
          if (change.destination && !fs.existsSync(original)) {
            await deletedFile({ ...normalized, tool_use_id: `${normalized.tool_use_id}:move` }, original);
          }
          outputs.push(runHook("ruff-format-check", normalized));
        }
      }
    }
  } else {
    outputs.push(runHook(hook, payload));
    if (hook === "post-bash" && !failed(input.tool_response)) {
      const read = powershellRead(input.tool_input?.command, cwd);
      const response = input.tool_response;
      const content = typeof response === "string" ? response
        : response?.stdout ?? response?.output;
      if (read && typeof content === "string" && content.length) {
        outputs.push(runHook("post-read", {
          ...payload, tool_name: "Read", tool_input: read, tool_response: content,
          tool_use_id: `${input.tool_use_id || randomUUID()}:read`,
        }));
      }
    }
    if (hook === "post-write" && !failed(input.tool_response)) {
      outputs.push(runHook("ruff-format-check", payload));
    }
  }
  emit(outputs);
}

let raw = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => { raw += chunk; });
process.stdin.on("end", () => main(raw).catch((error) => {
  process.stderr.write(`OpenWolf compatibility hook: ${error.message}\n`);
  process.exitCode = 1;
}));
