"""Generate environment-specific pip-tools locks and audit their input fingerprint.

Generation preserves existing pins. Run separately on each supported environment;
it never installs application dependencies or touches the operator's GPU venv.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "requirements-locks.json"


def digest(path: Path) -> str:
    # Git checkouts may use CRLF on Windows and LF on CI. These are text inputs.
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def lock_names() -> tuple[str, str]:
    version = sys.version_info[:2]
    system = platform.system().lower()
    if version != (3, 11) or system not in {"windows", "linux"}:
        raise ValueError("generate locks on Python 3.11 on Windows or Linux")
    suffix = "" if system == "windows" else "-py311-linux"
    return f"requirements-runtime{suffix}.lock", f"requirements-dev{suffix}.lock"


def generate() -> None:
    runtime, development = lock_names()
    input_fingerprint = digest(ROOT / "pyproject.toml")
    seed = ROOT / "requirements-runtime.lock"
    if not (ROOT / runtime).exists() and seed.exists():
        shutil.copyfile(seed, ROOT / runtime)
    env = {**os.environ, "PIP_CACHE_DIR": str(ROOT / "tmp" / "pip-cache")}
    for filename, extra in ((runtime, []), (development, ["--extra", "dev", "-c", runtime])):
        command = [
            sys.executable,
            "-m",
            "piptools",
            "compile",
            "--generate-hashes",
            "--no-emit-index-url",
            "--strip-extras",
            "--allow-unsafe",
            "--cache-dir",
            str(ROOT / "tmp" / "pip-tools"),
            *extra,
            "--output-file",
            filename,
            "pyproject.toml",
        ]
        env["CUSTOM_COMPILE_COMMAND"] = "python -m scripts.manage_dependencies --generate"
        subprocess.run(command, cwd=ROOT, env=env, check=True)
    if digest(ROOT / "pyproject.toml") != input_fingerprint:
        raise ValueError("pyproject changed during lock generation; regenerate this pair")
    record(runtime, development, input_fingerprint)


def record(runtime: str, development: str, input_fingerprint: str) -> None:
    """Record only this environment; other environments still require regeneration."""
    manifest = (
        json.loads(MANIFEST.read_text(encoding="utf-8"))
        if MANIFEST.exists()
        else {"schema_version": 1, "environments": {}}
    )
    key = f"{platform.system().lower()}-py{sys.version_info.major}{sys.version_info.minor}"
    manifest["environments"][key] = {
        "pyproject_sha256": input_fingerprint,
        "locks": {name: digest(ROOT / name) for name in (runtime, development)},
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def check() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not {"windows-py311", "linux-py311"} <= manifest["environments"].keys():
        raise ValueError("generate all supported Windows/Linux lock environments")
    for key, value in manifest["environments"].items():
        if value["pyproject_sha256"] != digest(ROOT / "pyproject.toml"):
            raise ValueError(f"pyproject changed: regenerate {key} locks")
        for name, expected in value["locks"].items():
            if digest(ROOT / name) != expected:
                raise ValueError(f"lock fingerprint changed: {name}")
    print("Dependency declarations and recorded locks agree.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--generate", action="store_true")
    action.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.generate:
        generate()
    else:
        check()


if __name__ == "__main__":
    main()
