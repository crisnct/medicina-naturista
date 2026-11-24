"""The only process with the Docker socket: start, stop and status for a fixed list of vLLM servers.

Standard library only, because it runs unbuilt in the `vllm-supervisor` Compose service. The app
reaches it on a network no other container joins, so it needs no credential of its own. Every
start first unloads the host Ollama models that hold GPU memory, because vLLM exits on startup
when it cannot allocate its share.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import socket
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import quote, urlsplit

logger = logging.getLogger("naturist.vllm_supervisor")

# A container is named medicina-<service>; the Compose label must agree before anything changes.
MANAGED_SERVICES = ("vllm-qwen35", "vllm-qwen25")
# Visible so the app can refuse to warm up beside it, never changed by the app: it may be
# mid-translation (vllm-translate) or mid-build (vllm-embed).
OBSERVED_SERVICES = ("vllm-translate", "vllm-embed")
# The index build starts and stops this one itself, from the host; the app's
# report models never do, so it is listed above as observed and a report refuses to start beside it.
BUILD_SERVICE = "vllm-embed"
STARTABLE_SERVICES = (*MANAGED_SERVICES, BUILD_SERVICE)
DOCKER_SOCKET = "/var/run/docker.sock"
LISTEN_PORT = 8080
STOP_GRACE_SECONDS = 30
# The stop call blocks for the grace period, so the socket timeout must outlast it.
DOCKER_TIMEOUT_SECONDS = STOP_GRACE_SECONDS + 30
# Only an Ollama of this machine shares the GPU; a cloud address is never told to unload.
OLLAMA_LOCAL_HOSTS = frozenset({"host.docker.internal", "localhost", "127.0.0.1", "::1"})
OLLAMA_UNLOAD_SECONDS = 30.0
OLLAMA_POLL_SECONDS = 2.0
OLLAMA_REQUEST_TIMEOUT_SECONDS = 10.0


class SupervisorError(Exception):
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
        raise SupervisorError(503, "DOCKER_UNAVAILABLE") from None
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
        raise SupervisorError(503, "DOCKER_UNAVAILABLE")
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


# The Ollama of this machine without the /v1 suffix, or None when no local Ollama is configured.
def _ollama_base() -> str | None:
    base = os.environ.get("OLLAMA_API_BASE", "").strip().rstrip("/").removesuffix("/v1")
    if not base or (urlsplit(base).hostname or "") not in OLLAMA_LOCAL_HOSTS:
        return None
    return base


def _ollama(url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, method="GET" if data is None else "POST")
    request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=OLLAMA_REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read() or b"{}")


# The model that embeds questions runs on the CPU (size_vram 0), so it stays loaded.
def _ollama_gpu_models(base: str) -> list[str]:
    models = _ollama(f"{base}/api/ps").get("models") or []
    return [str(item["name"]) for item in models if int(item.get("size_vram") or 0) > 0]


# A model left on the GPU makes the vLLM server exit on startup, so a start is refused instead.
# An Ollama that does not answer holds nothing that could be released through it.
def unload_ollama() -> None:
    base = _ollama_base()
    if base is None:
        return
    try:
        models = _ollama_gpu_models(base)
        for model in models:
            _ollama(f"{base}/api/generate", {"model": model, "keep_alive": 0})
        deadline = time.monotonic() + OLLAMA_UNLOAD_SECONDS
        while models:
            if time.monotonic() >= deadline:
                logger.error("ollama_unload_timeout models=%s", ",".join(models))
                raise SupervisorError(409, "OLLAMA_GPU_BUSY")
            time.sleep(OLLAMA_POLL_SECONDS)
            models = _ollama_gpu_models(base)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.warning("ollama_unload_skipped type=%s", type(exc).__name__)
        return
    logger.info("ollama_gpu_free")


def start_service(service: str) -> dict[str, Any]:
    if service not in STARTABLE_SERVICES:
        raise SupervisorError(404, "UNKNOWN_SERVICE")
    current = status_all()
    everything = {**current["managed"], **current["observed"]}
    if everything[service]["state"] == "missing":
        raise SupervisorError(409, "CONTAINER_MISSING")
    # A start that fails on the port the report servers share leaves that container without a
    # working alias or port on its next start, so such a start must never be attempted.
    others = dict(everything)
    others.pop(service)
    if any(item["state"] in {"running", "restarting"} for item in others.values()):
        raise SupervisorError(409, "ANOTHER_SERVER_RUNNING")
    if everything[service]["state"] not in {"running", "restarting"}:
        unload_ollama()
    status, _ = _docker("POST", f"/containers/{quote(_container_name(service))}/start")
    if status not in {204, 304}:
        logger.error("docker_start_failed service=%s status=%s", service, status)
        raise SupervisorError(502, "START_FAILED")
    logger.info("service_started service=%s", service)
    return service_status(service)


# Answers only after the container has exited, which frees its GPU memory (measured).
def stop_service(service: str) -> dict[str, Any]:
    if service not in STARTABLE_SERVICES:
        raise SupervisorError(404, "UNKNOWN_SERVICE")
    if service_status(service)["state"] == "missing":
        raise SupervisorError(409, "CONTAINER_MISSING")
    path = f"/containers/{quote(_container_name(service))}/stop?t={STOP_GRACE_SECONDS}"
    status, _ = _docker("POST", path)
    if status not in {204, 304}:
        logger.error("docker_stop_failed service=%s status=%s", service, status)
        raise SupervisorError(502, "STOP_FAILED")
    result = service_status(service)
    if result["state"] in {"running", "restarting"}:
        raise SupervisorError(502, "STOP_FAILED")
    logger.info("service_stopped service=%s", service)
    return result


class _Handler(BaseHTTPRequestHandler):
    # One change at a time: a start must not race the stop that makes it safe.
    change_lock = threading.Lock()

    def _reply(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path != "/status":
            return self._reply(404, {"error": "NOT_FOUND"})
        try:
            self._reply(200, status_all())
        except SupervisorError as exc:
            self._reply(exc.status, {"error": exc.code})

    def do_POST(self) -> None:
        parts = self.path.strip("/").split("/")
        if len(parts) != 2 or parts[0] not in {"start", "stop"}:
            return self._reply(404, {"error": "NOT_FOUND"})
        action = start_service if parts[0] == "start" else stop_service
        try:
            with self.change_lock:
                self._reply(200, action(parts[1]))
        except SupervisorError as exc:
            self._reply(exc.status, {"error": exc.code})

    # The request line is already logged by the operations; keep the access log out of it.
    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    server = ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), _Handler)
    logger.info(
        "supervisor_listening port=%s services=%s", LISTEN_PORT, ",".join(STARTABLE_SERVICES)
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
