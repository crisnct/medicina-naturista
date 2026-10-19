#!/usr/bin/env node
// PostToolUse(Write|Edit|MultiEdit) advisory: after a .py file under src/ is
// written, check it against `ruff format` and `ruff check` — the two gates the
// CI `static` job runs. Catches a formatting-only CI failure immediately
// instead of after a push.
//
// Exit 0 = silent pass. Exit 2 = feedback to the model (stderr is shown).
// Ruff missing, or any internal error, is a silent pass: this hook must never
// block work over its own setup.

"use strict";

const { execFileSync } = require("node:child_process");
const { existsSync } = require("node:fs");
const path = require("node:path");

function check(raw) {
  try {
    main(raw);
  } catch {
    process.exit(0); // never fail the turn because the guard broke
  }
}

// Explicit file checks also work in hosts without Claude's PostToolUse events.
if (process.argv[2] === "--file" && process.argv[3]) {
  check(JSON.stringify({ file_path: path.resolve(process.argv[3]) }));
} else {
  let raw = "";
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", (c) => (raw += c));
  process.stdin.on("end", () => check(raw));
}

function main(raw) {
  const root = process.env.CLAUDE_PROJECT_DIR || process.cwd();
  const payload = JSON.parse(raw || "{}");
  const file = payload?.tool_input?.file_path ?? payload?.file_path;
  if (!file || !file.endsWith(".py")) process.exit(0);

  // Only files ruff is configured for: pyproject sets src/ as the target and
  // excludes the vendored dictionaries and the one-off icd10 scripts.
  const rel = path.relative(root, file).split(path.sep).join("/");
  if (!rel.startsWith("src/")) process.exit(0);
  if (rel.startsWith("src/scripts/dictionaires/")) process.exit(0);
  if (rel.startsWith("src/scripts/icd10_work/")) process.exit(0);
  if (!existsSync(file)) process.exit(0);

  const ruff = findRuff(root);
  if (!ruff) process.exit(0); // no ruff here — say nothing

  const problems = [];

  const fmt = run(ruff, ["format", "--check", file], root);
  if (fmt.status === 1) problems.push("unformatted (`ruff format --check` fails)");

  const lint = run(ruff, ["check", file], root);
  if (lint.status === 1) {
    const detail = (lint.stdout || "").trim().split("\n").slice(0, 10).join("\n");
    problems.push(`lint errors:\n${detail}`);
  }

  if (!problems.length) process.exit(0);

  process.stderr.write(
    `ruff: ${rel} would fail the CI \`static\` job — ${problems.join("; ")}\n\n` +
      `Fix it now, before moving on:\n` +
      `  ${ruff.display} format ${rel}\n` +
      `  ${ruff.display} check --fix ${rel}\n` +
      `Then re-read the file; formatting may have changed lines you are editing.\n`,
  );
  process.exit(2);
}

// Prefer the project venv (this project's documented setup), then a venv
// python -m ruff, then whatever is on PATH.
//
// On Windows `execFileSync` cannot resolve a `.cmd`/`.bat` shim the way a
// shell can — it fails with EINVAL — so PATH lookup goes through `python -m
// ruff` and an explicit shim probe rather than a bare `ruff`.
function findRuff(root) {
  const candidates = [
    [path.join(root, ".venv", "Scripts", "ruff.exe"), []],
    [path.join(root, ".venv", "bin", "ruff"), []],
    [path.join(root, ".venv", "Scripts", "python.exe"), ["-m", "ruff"]],
    [path.join(root, ".venv", "bin", "python"), ["-m", "ruff"]],
  ];
  for (const [bin, prefix] of candidates) {
    if (existsSync(bin)) {
      return { bin, prefix, display: prefix.length ? `"${bin}" -m ruff` : `"${bin}"` };
    }
  }
  for (const [bin, prefix] of [
    ["ruff.exe", []],
    ["ruff", []],
    ["python", ["-m", "ruff"]],
    ["python3", ["-m", "ruff"]],
  ]) {
    try {
      execFileSync(bin, [...prefix, "--version"], { stdio: "ignore", timeout: 5000 });
      return { bin, prefix, display: prefix.length ? `${bin} -m ruff` : bin };
    } catch {
      /* try the next one */
    }
  }
  return null;
}

function run(ruff, args, cwd) {
  try {
    const stdout = execFileSync(ruff.bin, [...ruff.prefix, ...args], {
      cwd,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      timeout: 10000,
    });
    return { status: 0, stdout };
  } catch (error) {
    // status 1 = ruff reported problems; anything else is a tool failure we ignore.
    return { status: error.status === 1 ? 1 : 0, stdout: error.stdout || "" };
  }
}
