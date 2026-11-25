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
import subprocess
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
STOP_WAIT_SECONDS = 15.0
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
            creationflags=CREATE_NO_WINDOW,
            check=True,
        ).stdout
        free, total = (float(value) for value in output.splitlines()[0].split(","))
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None, None
    return round(free / 1024, 1), round(total / 1024, 1)


# The plan's figures, from the text `coli plan` prints; unknown lines are ignored.
def parse_plan(output: str) -> dict[str, Any]:
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
        "ramMinimumGb": round(dense + runtime + RAM_MINIMUM_MARGIN_GB, 1)
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

    def healthy(self) -> bool:
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
        return {
            "ramAvailableGb": ram_available_gb(),
            "vramFreeGb": vram_free,
            "vramTotalGb": vram_total,
            "running": self.running(),
            "healthy": self.healthy(),
        }

    # The memory must be measured with the server stopped: a running one already holds its share.
    def check(self) -> dict[str, Any]:
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
                creationflags=CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.error("plan_failed type=%s", type(exc).__name__)
            raise AgentError(502, "PLAN_FAILED") from None
        plan = parse_plan(f"{completed.stdout}\n{completed.stderr}")
        # `coli plan` sizes its own cache; the server runs with the configured one.
        if self.config.cap > 0 and plan["planValid"]:
            plan["expertsPerLayer"] = self.config.cap
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
                        *(["--cap", str(self.config.cap)] if self.config.cap > 0 else []),
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
        return environment

    def stop(self) -> dict[str, Any]:
        with self.change_lock:
            if self._process is not None and self._process.poll() is None:
                # coli.cmd starts Python, which starts the engine: the whole tree must go.
                subprocess.run(
                    ["taskkill", "/T", "/F", "/PID", str(self._process.pid)],
                    capture_output=True,
                    timeout=COMMAND_TIMEOUT_SECONDS,
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
    def start_ollama(self) -> dict[str, Any]:
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
        default=Path(
            r"C:\Colibri\Models\Qwen3.8-Flash-Next-GGUF\UD-Q2_0"
            r"\Qwen3.8-Flash-Next-UD-Q2_0.colibri"
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
        "agent_listening port=%s serve_port=%s model_id=%s threads=%s cap=%s",
        config.port,
        config.serve_port,
        config.model_id,
        config.threads or "default",
        config.cap or "auto",
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
