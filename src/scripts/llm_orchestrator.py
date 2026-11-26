"""The only process with the Docker socket: start, stop and status for a fixed list of vLLM servers.

Standard library only, because it runs unbuilt in the `llm-orchestrator` Compose service. The app
reaches it on a network no other container joins, so it needs no credential of its own. Every
start first has the LLM host agent (src/scripts/llm_host_agent.py) stop the Colibri server and
unload the host Ollama models that hold GPU memory, because vLLM exits on startup when it cannot
allocate its share. It never calls Ollama itself.

It is also the app's only way to the host agent: /host-agent/<path> relays a fixed list of the
agent's endpoints (Colibri and the host Ollama), and its changes share the lock of the vLLM starts.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import socket
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import quote

logger = logging.getLogger("naturist.llm_orchestrator")

# A container is named medicina-<service>; the Compose label must agree before anything changes.
MANAGED_SERVICES = ("vllm-qwen35", "vllm-qwen25")
# Visible so the app can refuse to warm up beside it; the app stops one only when the admin unloads
# it from the window, since it may be mid-translation (vllm-translate) or mid-build (vllm-embed).
OBSERVED_SERVICES = ("vllm-translate", "vllm-embed")
# The index build starts and stops this one itself, from the host; the app's
# report models never do, so it is listed above as observed and a report refuses to start beside it.
BUILD_SERVICE = "vllm-embed"
STARTABLE_SERVICES = (*MANAGED_SERVICES, BUILD_SERVICE)
# The admin may unload any local model from the app's window, so every server can be stopped;
# vllm-translate is still never started here.
STOPPABLE_SERVICES = (*STARTABLE_SERVICES, "vllm-translate")
DOCKER_SOCKET = "/var/run/docker.sock"
LISTEN_PORT = 8080
STOP_GRACE_SECONDS = 30
# The stop call blocks for the grace period, so the socket timeout must outlast it.
DOCKER_TIMEOUT_SECONDS = STOP_GRACE_SECONDS + 30
# Colibri holds ~9 GB of VRAM and most of the RAM while it is loaded. The host agent stops it
# gracefully (up to 60 s, so the expert history is written) and then by force (15 s), so the stop
# gets that long and a margin.
COLIBRI_STATUS_TIMEOUT_SECONDS = 15.0
COLIBRI_STOP_TIMEOUT_SECONDS = 120.0
# The agent waits up to 30 s for the Ollama models to leave the GPU, after requests of up to 10 s.
OLLAMA_UNLOAD_TIMEOUT_SECONDS = 60.0
# The host agent's endpoints the app may call, as /host-agent<path> here: Colibri's status, memory
# check, start and stop, the stop, start, unload and load of the host Ollama, the release of one
# Ollama model, and the loaded models.
HOST_AGENT_PREFIX = "/host-agent"
HOST_AGENT_RELAY = frozenset(
    {
        ("GET", "/status"),
        ("GET", "/models"),
        ("POST", "/check"),
        ("POST", "/start"),
        ("POST", "/stop"),
        ("POST", "/ollama/stop"),
        ("POST", "/ollama/start"),
        ("POST", "/ollama/unload"),
        ("POST", "/ollama/unload?all=1"),
        ("POST", "/ollama/load"),
        ("POST", "/ollama/release"),
    }
)
# The agent's /check runs `coli plan` (up to 180 s); /ollama/load first stops Colibri (up to 75 s),
# waits up to 60 s for Ollama to start and up to 180 s for the model to load.
HOST_AGENT_RELAY_TIMEOUT_SECONDS = 330.0
# The largest body relayed to the agent (a load request is a few hundred bytes).
HOST_AGENT_MAX_BODY_BYTES = 16384


class OrchestratorError(Exception):
    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


class _DockerConnection(http.client.HTTPConnection):
    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.settimeout(DOCKER_TIMEOUT_SECONDS)
        self.sock.connect(DOCKER_SOCKET)


def _docker(method: str, path: str) -> tuple[int, bytes]:
    connection = _DockerConnection("localhost", timeout=DOCKER_TIMEOUT_SECONDS)
    try:
        connection.request(method, path)
        response = connection.getresponse()
        return response.status, response.read()
    except OSError as exc:
        logger.error("docker_unreachable type=%s", type(exc).__name__)
        raise OrchestratorError(503, "DOCKER_UNAVAILABLE") from None
    finally:
        connection.close()


def _container_name(service: str) -> str:
    return f"medicina-{service}"


def service_status(service: str) -> dict[str, Any]:
    status, body = _docker("GET", f"/containers/{quote(_container_name(service))}/json")
    if status == 404:
        return {"state": "missing", "exitCode": None, "oomKilled": False}
    if status != 200:
        logger.error("docker_inspect_failed service=%s status=%s", service, status)
        raise OrchestratorError(503, "DOCKER_UNAVAILABLE")
    data = json.loads(body)
    # A foreign container that took the name is reported as absent, and so is never touched.
    labels = data.get("Config", {}).get("Labels") or {}
    if labels.get("com.docker.compose.service") != service:
        logger.error("docker_label_mismatch service=%s", service)
        return {"state": "missing", "exitCode": None, "oomKilled": False}
    state = data["State"]
    return {
        "state": state["Status"],
        "exitCode": state.get("ExitCode"),
        "oomKilled": bool(state.get("OOMKilled")),
    }


def status_all() -> dict[str, Any]:
    return {
        "managed": {service: service_status(service) for service in MANAGED_SERVICES},
        "observed": {service: service_status(service) for service in OBSERVED_SERVICES},
    }


def _host_agent() -> str | None:
    return os.environ.get("LLM_HOST_AGENT_URL", "").strip().rstrip("/") or None


# One call to the host agent: its status and body, whatever the status. An agent that is not
# configured or does not answer is HOST_AGENT_UNAVAILABLE.
def _agent_call(method: str, path: str, timeout: float, body: bytes = b"") -> tuple[int, bytes]:
    base = _host_agent()
    if base is None:
        raise OrchestratorError(503, "HOST_AGENT_UNAVAILABLE")
    data = body if method == "POST" else None
    request = urllib.request.Request(f"{base}{path}", data=data, method=method)
    if body:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except OSError as exc:
        logger.warning("host_agent_unreachable path=%s type=%s", path, type(exc).__name__)
        raise OrchestratorError(503, "HOST_AGENT_UNAVAILABLE") from None


# The app reaches the host agent only through this relay, never directly; one change at a time
# covers the agent's changes too, so a Colibri start cannot race a vLLM start.
def relay_host_agent(method: str, path: str, body: bytes = b"") -> tuple[int, bytes]:
    if (method, path) not in HOST_AGENT_RELAY:
        raise OrchestratorError(404, "NOT_FOUND")
    status, reply = _agent_call(method, path, HOST_AGENT_RELAY_TIMEOUT_SECONDS, body)
    if status >= 400:
        logger.warning("host_agent_refused path=%s status=%s", path, status)
    return status, reply


# A model left on the GPU makes the vLLM server exit on startup, so a start is refused when the
# agent reports models still loaded (409). Without an agent, or with one that does not answer,
# there is no host Ollama that could be released through it.
def unload_ollama() -> None:
    if _host_agent() is None:
        return
    try:
        status, body = _agent_call("POST", "/ollama/unload", OLLAMA_UNLOAD_TIMEOUT_SECONDS)
    except OrchestratorError:
        return
    if status == 409:
        raise OrchestratorError(409, "OLLAMA_GPU_BUSY")
    if status != 200:
        logger.warning("ollama_unload_skipped status=%s", status)
        return
    logger.info("ollama_unloaded")


# Without an agent there is no Colibri to stop, and one that does not answer has not started any;
# a loaded Colibri that refuses to stop keeps the GPU, so the start is refused instead.
def stop_colibri() -> None:
    if _host_agent() is None:
        return
    try:
        status, body = _agent_call("GET", "/status", COLIBRI_STATUS_TIMEOUT_SECONDS)
        running = status == 200 and bool(json.loads(body or b"{}").get("running"))
    except (OrchestratorError, ValueError, AttributeError):
        return
    if not running:
        return
    try:
        status, _ = _agent_call("POST", "/stop", COLIBRI_STOP_TIMEOUT_SECONDS)
    except OrchestratorError:
        status = 503
    if status != 200:
        logger.error("colibri_stop_failed status=%s", status)
        raise OrchestratorError(409, "COLIBRI_BUSY")
    logger.info("colibri_stopped")


def start_service(service: str) -> dict[str, Any]:
    if service not in STARTABLE_SERVICES:
        raise OrchestratorError(404, "UNKNOWN_SERVICE")
    current = status_all()
    everything = {**current["managed"], **current["observed"]}
    if everything[service]["state"] == "missing":
        raise OrchestratorError(409, "CONTAINER_MISSING")
    # A start that fails on the port the report servers share leaves that container without a
    # working alias or port on its next start, so such a start must never be attempted.
    others = dict(everything)
    others.pop(service)
    if any(item["state"] in {"running", "restarting"} for item in others.values()):
        raise OrchestratorError(409, "ANOTHER_SERVER_RUNNING")
    if everything[service]["state"] not in {"running", "restarting"}:
        stop_colibri()
        unload_ollama()
    status, _ = _docker("POST", f"/containers/{quote(_container_name(service))}/start")
    if status not in {204, 304}:
        logger.error("docker_start_failed service=%s status=%s", service, status)
        raise OrchestratorError(502, "START_FAILED")
    logger.info("service_started service=%s", service)
    return service_status(service)


# Answers only after the container has exited, which frees its GPU memory (measured).
def stop_service(service: str) -> dict[str, Any]:
    if service not in STOPPABLE_SERVICES:
        raise OrchestratorError(404, "UNKNOWN_SERVICE")
    if service_status(service)["state"] == "missing":
        raise OrchestratorError(409, "CONTAINER_MISSING")
    path = f"/containers/{quote(_container_name(service))}/stop?t={STOP_GRACE_SECONDS}"
    status, _ = _docker("POST", path)
    if status not in {204, 304}:
        logger.error("docker_stop_failed service=%s status=%s", service, status)
        raise OrchestratorError(502, "STOP_FAILED")
    result = service_status(service)
    if result["state"] in {"running", "restarting"}:
        raise OrchestratorError(502, "STOP_FAILED")
    logger.info("service_stopped service=%s", service)
    return result


class _Handler(BaseHTTPRequestHandler):
    # One change at a time: a start must not race the stop that makes it safe.
    change_lock = threading.Lock()

    def _reply(self, status: int, payload: dict[str, Any]) -> None:
        self._send(status, json.dumps(payload).encode())

    def _send(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # The request body and the agent's answer pass as they are, its error codes included.
    def _relay(self, method: str) -> None:
        path = self.path.removeprefix(HOST_AGENT_PREFIX)
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 <= length <= HOST_AGENT_MAX_BODY_BYTES:
            return self._reply(413, {"error": "BODY_TOO_LARGE"})
        body = self.rfile.read(length) if length else b""
        try:
            if method == "GET":
                self._send(*relay_host_agent(method, path))
            else:
                with self.change_lock:
                    self._send(*relay_host_agent(method, path, body))
        except OrchestratorError as exc:
            self._reply(exc.status, {"error": exc.code})

    def do_GET(self) -> None:
        if self.path.startswith(f"{HOST_AGENT_PREFIX}/"):
            return self._relay("GET")
        if self.path != "/status":
            return self._reply(404, {"error": "NOT_FOUND"})
        try:
            self._reply(200, status_all())
        except OrchestratorError as exc:
            self._reply(exc.status, {"error": exc.code})

    def do_POST(self) -> None:
        if self.path.startswith(f"{HOST_AGENT_PREFIX}/"):
            return self._relay("POST")
        parts = self.path.strip("/").split("/")
        if len(parts) != 2 or parts[0] not in {"start", "stop"}:
            return self._reply(404, {"error": "NOT_FOUND"})
        action = start_service if parts[0] == "start" else stop_service
        try:
            with self.change_lock:
                self._reply(200, action(parts[1]))
        except OrchestratorError as exc:
            self._reply(exc.status, {"error": exc.code})

    # The request line is already logged by the operations; keep the access log out of it.
    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    server = ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), _Handler)
    logger.info(
        "orchestrator_listening port=%s services=%s", LISTEN_PORT, ",".join(STARTABLE_SERVICES)
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
