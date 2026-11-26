"""Windows host agent for Colibri: memory status, `coli plan` checks, start and stop of the server.

Standard library only, run by the system Python at logon (colibri_agent_startup.ps1), because
the app runs in Docker and can neither read the host's memory nor start a Windows process. It
loads no model itself. It listens on loopback only and accepts no Host header but its own names,
so a web page cannot reach it through DNS rebinding; Docker Desktop forwards
host.docker.internal to the host's loopback, which is how the app calls it.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import logging
import os
import re
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

logger = logging.getLogger("naturist.colibri_agent")

LISTEN_HOST = "127.0.0.1"
ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "host.docker.internal"})
PLAN_TIMEOUT_SECONDS = 180
COMMAND_TIMEOUT_SECONDS = 20
HEALTH_TIMEOUT_SECONDS = 2.0
PORT_PROBE_SECONDS = 0.3
STOP_WAIT_SECONDS = 15.0
# The engine writes its expert history (.coli_usage), from which the next start puts the most used
# experts on the GPU, only when the server ends on its own; Windows has no SIGTERM, so a forced
# kill lost it and the GPU took its experts in file order. With the history of one report a decode
# step took 517 ms instead of 616 (2026-11-25). `coli stop` asks the server through a file in the
# temp folder (it inherits the agent's), and the server lets the engine drain for up to 30 s.
GRACEFUL_STOP_SECONDS = 60.0
# Docker Desktop's VM and what frees its page cache (run as root inside it, see release_wsl_cache).
WSL_DISTRO = "docker-desktop"
WSL_RELEASE_SCRIPT = (
    "sync; echo 3 > /proc/sys/vm/drop_caches; echo 1 > /proc/sys/vm/compact_memory; free -m"
)
# Every child gets stdin=DEVNULL: under the logon task's pythonw the agent has no console, and
# `wsl` and `coli plan` then hung until their timeouts (2026-11-26).
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200
OLLAMA_VERSION_URL = "http://127.0.0.1:11434/api/version"
OLLAMA_START_SECONDS = 60.0
# One expert slot per layer is tiny next to the dense part and the runtime; the server also keeps
# a margin outside its budget. Together they are about this much on top of dense + runtime.
RAM_MINIMUM_MARGIN_GB = 1.0
DEFAULT_THREADS = 23
# Expert slots per layer (~0.8 GB per 10). The planner picked 42 with ~14 GB available, and a
# 1k-token prompt then gave no token in 12 minutes; 100 read it in 105 s (2026-11-25). One prompt
# chunk needs more experts per layer than a small cache holds, so the reads go one by one.
DEFAULT_CAP = 110
# With less RAM the cap shrinks to what is left after the server's fixed part (resident weights,
# KV and state, prefill workspace, prefix store: ~8 GiB) and a 1 GiB margin, at ~0.068 GiB a slot
# per layer: at ~15 GB available cap 110 made Windows page and read a prompt at 19 tok/s, cap 88
# at 28 tok/s, with the same decode (2026-11-26).
CAP_FIXED_GB = 9.0
CAP_SLOT_GB = 0.068
MIN_ADAPTIVE_CAP = 40
# Prompt rows whose routed experts the CPU computes in one pass (Q38_PREFILL_BATCH_ROWS). With
# Colibri's 32 the CPU expanded every expert's 2-bit weights again for each 32 rows: a
# 3,100-token prompt read at 10.8 tok/s, at 2048 rows (one CUDA chain chunk) at 25.2 tok/s
# (2026-11-25). Bounded by the engine's 8192.
DEFAULT_PREFILL_ROWS = 2048
MAX_PREFILL_ROWS = 8192
# One row of Qwen3.8-Flash-Next's MoE prefill scratch (family_registry.py, moe_row_bytes: 512
# experts, top-10, hidden 2560, expert width 640). Colibri's workspace cap (64 MiB) holds ~240 of
# them, so the agent raises it to half a MiB a row; `coli plan` prices only the 64 MiB, so the
# rest is added to the RAM minimum.
# COLI_PREFIX_STORE_MB: the prompts Colibri keeps in RAM to reuse their beginning.
PREFIX_STORE_MIB = 512
# CUDA_EXPERT_GB, the VRAM Colibri may fill with its trunk and experts, is the free VRAM nvidia-smi
# reports less this much. With 10.5 of 11.0 GiB the GPU held 1,724 experts instead of 783, nothing
# spilled into shared memory, and a decode step took 360 ms instead of 501 (5.3 tok/s instead of
# 4.0; aiplans/2026-11-25-performanta-colibri.md).
VRAM_HEADROOM_GB = 0.5
PREFILL_ROW_KIB = 270
PREFILL_WORKSPACE_MIB_PER_ROW = 0.5
COLIBRI_PREFILL_WORKSPACE_MIB = 64

_GB_RE = r"([0-9]+(?:\.[0-9]+)?)\s*GB"
_RAM_RE = re.compile(
    rf"^\s*RAM\s+{_GB_RE} budget\s*·\s*{_GB_RE} dense\s*·\s*{_GB_RE} runtime"
    rf"(?:\s*·\s*{_GB_RE} warm experts)?(?:\s*·\s*cap\s+(\d+)/layer)?",
    re.MULTILINE,
)
_VRAM_RE = re.compile(rf"^\s*VRAM\s+{_GB_RE} hot tier", re.MULTILINE)
_HIT_RE = re.compile(r"^\s*hit\s+(\d+)%", re.MULTILINE)
_WARN_RE = re.compile(r"^\s*warn\s+(.+?)\s*$", re.MULTILINE)
_INVALID_RE = re.compile(r"invalid resource plan:\s*(.+)")
# The planner's own words when the RAM cannot hold even one expert slot per layer; the server then
# refuses to start ("invalid resource plan").
_NO_SLOT = "cannot hold one expert slot"


@dataclass(frozen=True)
class AgentConfig:
    colibri_dir: Path
    model: Path
    port: int
    serve_port: int
    ctx: int
    model_id: str
    log_file: Path
    # OMP_NUM_THREADS of the engine; 0 leaves Colibri's own default.
    threads: int = 0
    # Expert slots per layer of `coli serve --cap`; 0 lets Colibri's planner choose.
    cap: int = 0
    # Where Colibri keeps the prompts it read between runs (Q38_PREFIX_DISK).
    prefix_dir: Path = Path(r"C:\Colibri\prefix-cache")
    # The Ollama install whose processes a Colibri report stops (its tray app restarts it).
    ollama_dir: Path = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama"
    # Q38_PREFILL_BATCH_ROWS of the engine; 0 leaves Colibri's own 32.
    prefill_rows: int = 0

    @property
    def coli(self) -> Path:
        return self.colibri_dir / "coli.cmd"

    @property
    def health_url(self) -> str:
        return f"http://127.0.0.1:{self.serve_port}/health"


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


# Available physical memory, standby cache included: what Windows can hand to a new process.
def ram_available_gb() -> float:
    status = _MemoryStatus()
    status.dwLength = ctypes.sizeof(_MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError("GlobalMemoryStatusEx failed")
    return round(status.ullAvailPhys / 1024**3, 1)


# Free and total memory of the first NVIDIA GPU; None when nvidia-smi is missing or fails.
def vram_gb() -> tuple[float | None, float | None]:
    try:
        output = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.free,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            check=True,
        ).stdout
        free, total = (float(value) for value in output.splitlines()[0].split(","))
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None, None
    return round(free / 1024, 1), round(total / 1024, 1)


# Docker Desktop's WSL VM keeps the files it read as cache, and Windows gets that RAM back only
# once Linux frees it. Dropping the cache and compacting the free pages (WSL returns them in whole
# blocks) before the memory is measured leaves it to Colibri. A failure only logs: the report goes
# on with the RAM there is.
def release_wsl_cache() -> None:
    before = ram_available_gb()
    try:
        completed = subprocess.run(
            ["wsl", "-d", WSL_DISTRO, "-u", "root", "-e", "sh", "-c", WSL_RELEASE_SCRIPT],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=COMMAND_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("wsl_cache_release_failed type=%s", type(exc).__name__)
        return
    memory = next(
        (line.split() for line in completed.stdout.splitlines() if line.startswith("Mem:")), []
    )
    logger.info(
        "wsl_cache_released code=%s ram_available_gb_before=%s linux_free_mb=%s",
        completed.returncode,
        before,
        memory[3] if len(memory) > 3 else None,
    )


# The cache the available RAM leaves room for, never above the configured one; 0 keeps 0
# (Colibri's planner chooses).
def adaptive_cap(cap: int, available_gb: float) -> int:
    if cap <= 0:
        return cap
    room = int((available_gb - CAP_FIXED_GB) / CAP_SLOT_GB)
    return max(MIN_ADAPTIVE_CAP, min(cap, room))


# The scratch of a prefill pass beyond the 64 MiB `coli plan` counts, in GB.
def prefill_extra_gb(rows: int) -> float:
    return max(0.0, rows * PREFILL_ROW_KIB / 1024 - COLIBRI_PREFILL_WORKSPACE_MIB) / 1024


# The plan's figures, from the text `coli plan` prints; unknown lines are ignored. `extra_gb` is
# memory the server needs beyond what the planner prices.
def parse_plan(output: str, extra_gb: float = 0.0) -> dict[str, Any]:
    ram = _RAM_RE.search(output)
    vram = _VRAM_RE.search(output)
    hit = _HIT_RE.search(output)
    invalid = _INVALID_RE.search(output)
    warnings = list(_WARN_RE.findall(output))
    if invalid:
        warnings.append(invalid.group(1).strip())
    dense = float(ram.group(2)) if ram else None
    runtime = float(ram.group(3)) if ram else None
    cap = int(ram.group(5)) if ram and ram.group(5) else None
    valid = (
        ram is not None
        and invalid is None
        and (cap is None or cap > 0)
        and not any(_NO_SLOT in line for line in warnings)
    )
    return {
        "planValid": valid,
        "ramBudgetGb": float(ram.group(1)) if ram else None,
        "ramMinimumGb": round(dense + runtime + RAM_MINIMUM_MARGIN_GB + extra_gb, 1)
        if dense is not None and runtime is not None
        else None,
        "expertsPerLayer": cap,
        "vramHotTierGb": float(vram.group(1)) if vram else None,
        "expertResidencyPct": int(hit.group(1)) if hit else None,
        "planWarnings": warnings[:8],
    }


class Agent:
    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self._process: subprocess.Popen[bytes] | None = None
        # One change at a time: a start must not race the stop of the same server.
        self.change_lock = threading.Lock()

    # Windows answers a connection to a closed loopback port only after retrying it, so the HTTP
    # probe alone waited its whole 2 s timeout whenever the server was stopped, and /status took
    # 4-6 s. A listening port accepts in milliseconds.
    def healthy(self) -> bool:
        try:
            with socket.create_connection(
                ("127.0.0.1", self.config.serve_port), timeout=PORT_PROBE_SECONDS
            ):
                pass
        except OSError:
            return False
        try:
            with urllib.request.urlopen(
                self.config.health_url, timeout=HEALTH_TIMEOUT_SECONDS
            ) as response:
                return response.status == 200
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def running(self) -> bool:
        return (self._process is not None and self._process.poll() is None) or self.healthy()

    def status(self) -> dict[str, Any]:
        vram_free, vram_total = vram_gb()
        healthy = self.healthy()
        return {
            "ramAvailableGb": ram_available_gb(),
            "vramFreeGb": vram_free,
            "vramTotalGb": vram_total,
            "running": healthy or (self._process is not None and self._process.poll() is None),
            "healthy": healthy,
        }

    # The memory must be measured with the server stopped: a running one already holds its share.
    def check(self) -> dict[str, Any]:
        release_wsl_cache()
        status = self.status()
        if status["healthy"]:
            return {**status, "planValid": True, "planWarnings": []}
        try:
            completed = subprocess.run(
                [
                    str(self.config.coli),
                    "plan",
                    "--model",
                    str(self.config.model),
                    "--ctx",
                    str(self.config.ctx),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=PLAN_TIMEOUT_SECONDS,
                cwd=self.config.colibri_dir,
                stdin=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.error("plan_failed type=%s", type(exc).__name__)
            raise AgentError(502, "PLAN_FAILED") from None
        plan = parse_plan(
            f"{completed.stdout}\n{completed.stderr}", prefill_extra_gb(self.config.prefill_rows)
        )
        # `coli plan` sizes its own cache; the server runs with the configured one, made smaller
        # when the RAM is short.
        if self.config.cap > 0 and plan["planValid"]:
            plan["expertsPerLayer"] = adaptive_cap(self.config.cap, status["ramAvailableGb"])
        logger.info(
            "plan_checked valid=%s ram_available_gb=%s ram_budget_gb=%s experts_per_layer=%s",
            plan["planValid"],
            status["ramAvailableGb"],
            plan["ramBudgetGb"],
            plan["expertsPerLayer"],
        )
        return {**status, **plan}

    def start(self) -> dict[str, Any]:
        with self.change_lock:
            if self.running():
                return {"state": "running"}
            plan = self.check()
            if not plan["planValid"]:
                raise AgentError(409, "INSUFFICIENT_RESOURCES")
            self.config.log_file.parent.mkdir(parents=True, exist_ok=True)
            log = self.config.log_file.open("wb")
            try:
                self._process = subprocess.Popen(
                    [
                        str(self.config.coli),
                        "serve",
                        "--model",
                        str(self.config.model),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(self.config.serve_port),
                        "--ctx",
                        str(self.config.ctx),
                        "--gpu",
                        "auto",
                        "--auto-tier",
                        "--model-id",
                        self.config.model_id,
                        # The app calls from Docker with this Host header; Colibri's own
                        # DNS-rebinding guard answers 403 to any name it was not given.
                        "--allowed-host",
                        "host.docker.internal",
                        *(["--cap", str(plan["expertsPerLayer"])] if self.config.cap > 0 else []),
                    ],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    env=self._server_environment(),
                    cwd=self.config.colibri_dir,
                    creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
                )
            except OSError as exc:
                logger.error("start_failed type=%s", type(exc).__name__)
                raise AgentError(502, "START_FAILED") from None
            finally:
                log.close()
            logger.info("server_starting pid=%s", self._process.pid)
            return {"state": "starting"}

    # Qwen3.8 reads the prompt and computes the experts the GPU does not hold on the CPU, and
    # without OMP_NUM_THREADS the engine used 12 threads of the 32 here (24% CPU while reading a
    # prompt). Colibri's guide sets it to the physical core count.
    def _server_environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        if self.config.threads > 0:
            environment["OMP_NUM_THREADS"] = str(self.config.threads)
        # Every report starts with the same system prompt (~3,000 tokens). Colibri keeps the prompts
        # it read in memory and reuses a shared beginning; on disk the store survives the stop that
        # a report with another model causes, so the next Colibri report skips that part again.
        environment["Q38_PREFIX_DISK"] = "1"
        environment["Q38_PREFIX_DIR"] = str(self.config.prefix_dir)
        # In RAM that store grows to a quarter of the free memory (2.5-3.4 GB here), outside the
        # memory Colibri plans for its experts; the reports reuse only the system prompt (a 250 MiB
        # checkpoint), so the rest goes to the experts.
        environment["COLI_PREFIX_STORE_MB"] = str(PREFIX_STORE_MIB)
        # The GPU computes the experts it holds; Colibri's own allowance is the free VRAM Windows
        # reports less 1 GiB, which here left 1.1 GB, 783 experts, beside the 8 GB trunk.
        vram_free, _ = vram_gb()
        if vram_free is not None and vram_free > VRAM_HEADROOM_GB:
            environment["CUDA_EXPERT_GB"] = f"{vram_free - VRAM_HEADROOM_GB:.1f}"
        if self.config.prefill_rows > 0:
            environment["Q38_PREFILL_BATCH_ROWS"] = str(self.config.prefill_rows)
            environment["Q38_PREFILL_WORKSPACE_MIB"] = str(
                max(
                    COLIBRI_PREFILL_WORKSPACE_MIB,
                    round(self.config.prefill_rows * PREFILL_WORKSPACE_MIB_PER_ROW),
                )
            )
        return environment

    def stop(self) -> dict[str, Any]:
        with self.change_lock:
            if self.healthy():
                self._request_graceful_stop()
            if self._process is not None and self._process.poll() is None:
                # coli.cmd starts Python, which starts the engine: the whole tree must go.
                subprocess.run(
                    ["taskkill", "/T", "/F", "/PID", str(self._process.pid)],
                    capture_output=True,
                    timeout=COMMAND_TIMEOUT_SECONDS,
                    stdin=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW,
                )
            self._process = None
            # A server started before this agent (by hand, or by an agent that restarted) is found
            # by its command line, which names this Colibri folder.
            if self.healthy():
                self._kill_orphans()
            deadline = time.monotonic() + STOP_WAIT_SECONDS
            while self.healthy():
                if time.monotonic() >= deadline:
                    raise AgentError(502, "STOP_FAILED")
                time.sleep(0.5)
            logger.info("server_stopped")
            return {"state": "stopped"}

    # The request `coli stop` makes; the forced stop above remains for a server that ignores it.
    def _request_graceful_stop(self) -> None:
        request = Path(tempfile.gettempdir()) / f"coli-serve-{self.config.serve_port}.stop"
        try:
            request.write_text(f"{os.getpid()}\n", encoding="ascii")
        except OSError:
            return
        started = time.monotonic()
        while time.monotonic() - started < GRACEFUL_STOP_SECONDS and (
            self._process.poll() is None if self._process is not None else self.healthy()
        ):
            time.sleep(0.5)
        # Not taken (a server that does not watch for it) must not stop the next one at its start.
        request.unlink(missing_ok=True)
        logger.info("graceful_stop seconds=%.1f", time.monotonic() - started)

    def ollama_running(self) -> bool:
        try:
            with urllib.request.urlopen(
                OLLAMA_VERSION_URL, timeout=HEALTH_TIMEOUT_SECONDS
            ) as reply:
                return reply.status == 200
        except (urllib.error.URLError, OSError, ValueError):
            return False

    # Ollama keeps its server and every model runner in this process tree; a Colibri report needs
    # their RAM. The reply says whether it ran, so the app restarts it only in that case.
    def stop_ollama(self) -> dict[str, Any]:
        with self.change_lock:
            was_running = self.ollama_running()
            self._kill_under(self.config.ollama_dir)
            deadline = time.monotonic() + STOP_WAIT_SECONDS
            while self.ollama_running():
                if time.monotonic() >= deadline:
                    raise AgentError(502, "OLLAMA_STOP_FAILED")
                time.sleep(0.5)
            logger.info("ollama_stopped was_running=%s", was_running)
            return {"state": "stopped", "wasRunning": was_running}

    # Started through Explorer, as a click would: the tray app then reads the user's OLLAMA_*
    # variables and does not belong to this agent, so restarting the agent leaves it running.
    # A loaded Colibri is stopped first: Ollama's models need the RAM and VRAM it holds, and beside
    # them Windows paged Colibri out entirely while it sat idle (2026-11-26).
    def start_ollama(self) -> dict[str, Any]:
        if self.running():
            self.stop()
        with self.change_lock:
            if self.ollama_running():
                return {"state": "running"}
            app = self.config.ollama_dir / "ollama app.exe"
            if not app.is_file():
                raise AgentError(502, "OLLAMA_NOT_INSTALLED")
            try:
                subprocess.Popen(
                    ["explorer.exe", str(app)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW,
                )
            except OSError as exc:
                logger.error("ollama_start_failed type=%s", type(exc).__name__)
                raise AgentError(502, "OLLAMA_START_FAILED") from None
            deadline = time.monotonic() + OLLAMA_START_SECONDS
            while not self.ollama_running():
                if time.monotonic() >= deadline:
                    raise AgentError(504, "OLLAMA_START_TIMEOUT")
                time.sleep(1.0)
            logger.info("ollama_started")
            return {"state": "running"}

    def _kill_under(self, folder: Path) -> None:
        quoted = str(folder).replace("'", "''")
        script = (
            "Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and "
            f"$_.ExecutablePath.StartsWith('{quoted}\\', 'OrdinalIgnoreCase') }} | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
        )

    def _kill_orphans(self) -> None:
        folder = str(self.config.colibri_dir).replace("'", "''")
        script = (
            "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and "
            f"$_.CommandLine.Contains('{folder}') -and "
            "$_.Name -in 'python.exe','cmd.exe','qwen38.exe' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
        )


class AgentError(Exception):
    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


def _handler(agent: Agent) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _allowed(self) -> bool:
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
            if host in ALLOWED_HOSTS:
                return True
            self._reply(403, {"error": "HOST_NOT_ALLOWED"})
            return False

        def do_GET(self) -> None:
            if not self._allowed():
                return
            if self.path != "/status":
                return self._reply(404, {"error": "NOT_FOUND"})
            self._dispatch(agent.status)

        def do_POST(self) -> None:
            if not self._allowed():
                return
            actions = {
                "/check": agent.check,
                "/start": agent.start,
                "/stop": agent.stop,
                "/ollama/stop": agent.stop_ollama,
                "/ollama/start": agent.start_ollama,
            }
            action = actions.get(self.path)
            if action is None:
                return self._reply(404, {"error": "NOT_FOUND"})
            self._dispatch(action)

        def _dispatch(self, action: Any) -> None:
            try:
                self._reply(200, action())
            except AgentError as exc:
                self._reply(exc.status, {"error": exc.code})
            except OSError as exc:
                logger.error("request_failed path=%s type=%s", self.path, type(exc).__name__)
                self._reply(500, {"error": "AGENT_FAILED"})

        # The operations log what matters; keep the access log out of it.
        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def _arguments() -> tuple[AgentConfig, Path]:
    parser = argparse.ArgumentParser(description=__doc__)
    # pythonw (the logon task) has no console, so the agent writes its own log.
    parser.add_argument("--agent-log", type=Path, default=Path(r"C:\Colibri\agent.log"))
    parser.add_argument("--colibri-dir", type=Path, default=Path(r"C:\Colibri\colibri-v2.2.0"))
    parser.add_argument(
        "--model",
        type=Path,
        # Imported with the MTP head (`coli import ... --mtp MTP\mtp-...-shared-Q8_0.gguf --out`):
        # the head drafts three tokens a step, and at the same RAM the decode went from 4.9 to
        # 6.8 tok/s with the prompt read as fast (2026-11-26). Without the head: the plain
        # Qwen3.8-Flash-Next-UD-Q2_0.colibri next to it.
        default=Path(
            r"C:\Colibri\Models\Qwen3.8-Flash-Next-GGUF\UD-Q2_0"
            r"\Qwen3.8-Flash-Next-UD-Q2_0-mtp.colibri"
        ),
    )
    parser.add_argument("--port", type=int, default=8011)
    parser.add_argument("--serve-port", type=int, default=8010)
    parser.add_argument("--ctx", type=int, default=32768)
    parser.add_argument("--model-id", default="qwen3.8-flash-next-colibri")
    parser.add_argument("--log-file", type=Path, default=Path(r"C:\Colibri\serve.log"))
    # This laptop's 24 physical cores less one, as Colibri's Qwen3.8 guide runs it (the spare
    # core keeps the gateway and the OS from stalling the engine's threads); 0 keeps Colibri's
    # own default.
    parser.add_argument("--threads", type=int, default=DEFAULT_THREADS)
    parser.add_argument("--cap", type=int, default=DEFAULT_CAP)
    parser.add_argument("--prefix-dir", type=Path, default=Path(r"C:\Colibri\prefix-cache"))
    parser.add_argument("--prefill-rows", type=int, default=DEFAULT_PREFILL_ROWS)
    parser.add_argument(
        "--ollama-dir",
        type=Path,
        default=Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama",
    )
    args = parser.parse_args()
    if args.cap < 0:
        parser.error("--cap must be 0 (Colibri's planner) or a positive number")
    if args.threads < 0:
        parser.error("--threads must be 0 (Colibri's default) or a positive number")
    if not 0 <= args.prefill_rows <= MAX_PREFILL_ROWS:
        parser.error(f"--prefill-rows must be 0 (Colibri's 32) up to {MAX_PREFILL_ROWS}")
    for name in ("port", "serve_port"):
        if not 1 <= getattr(args, name) <= 65535:
            parser.error(f"--{name.replace('_', '-')} must be a valid TCP port")
    if not (args.colibri_dir / "coli.cmd").is_file():
        parser.error(f"coli.cmd not found in {args.colibri_dir}")
    if not args.model.is_dir():
        parser.error(f"model directory not found: {args.model}")
    config = AgentConfig(
        args.colibri_dir,
        args.model,
        args.port,
        args.serve_port,
        args.ctx,
        args.model_id,
        args.log_file,
        args.threads,
        args.cap,
        args.prefix_dir,
        args.ollama_dir,
        args.prefill_rows,
    )
    return config, args.agent_log


def main() -> None:
    config, agent_log = _arguments()
    agent_log.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=agent_log,
        encoding="utf-8",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    server = ThreadingHTTPServer((LISTEN_HOST, config.port), _handler(Agent(config)))
    logger.info(
        "agent_listening port=%s serve_port=%s model_id=%s threads=%s cap=%s prefill_rows=%s",
        config.port,
        config.serve_port,
        config.model_id,
        config.threads or "default",
        config.cap or "auto",
        config.prefill_rows or "default",
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
