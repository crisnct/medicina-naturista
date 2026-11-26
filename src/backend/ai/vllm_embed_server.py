"""Life cycle of the `vllm-embed` Compose service for an index build.

The build starts the server only when there is something to embed, waits until it serves the
model, and stops it afterwards (also after an error or Ctrl+C), so the GPU is free for Ollama
and the report servers again. Only the `llm-orchestrator` container has Docker access, so the
build asks it over its loopback port (LLM_ORCHESTRATOR_HOST_PORT) instead of calling Docker. The
orchestrator has the LLM host agent unload the host Ollama models that hold GPU memory before the
start; a running vLLM server is an error that names it, and nothing of it is stopped for the
operator. The server's flags come from `.env` through docker-compose.yaml."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx

from backend.ai.embedding_model import DEFAULT_MODEL, vllm_embed_url
from backend.config import settings

SERVICE = "vllm-embed"
_RUNNING_STATES = frozenset({"running", "restarting"})
_POLL_SECONDS = 3
# A stop waits for the container's grace period (30 s) before the orchestrator answers; a start
# first stops a loaded Colibri (up to 120 s) and unloads Ollama (up to 30 s).
_ORCHESTRATOR_TIMEOUT = httpx.Timeout(240.0, connect=5.0)
_PROBE_TIMEOUT = httpx.Timeout(3.0, connect=2.0)


def _orchestrator_url() -> str:
    return f"http://127.0.0.1:{settings.llm_orchestrator_host_port}"


# One call to the orchestrator; its error codes (CONTAINER_MISSING, ANOTHER_SERVER_RUNNING, ...) are
# part of the message, so the operator sees what to fix.
def _orchestrator(method: str, path: str) -> dict[str, Any]:
    try:
        response = httpx.request(
            method, f"{_orchestrator_url()}{path}", timeout=_ORCHESTRATOR_TIMEOUT
        )
    except httpx.HTTPError:
        raise RuntimeError(
            "VLLM_EMBED_ORCHESTRATOR_UNAVAILABLE: the llm-orchestrator does not answer on "
            f"{_orchestrator_url()}. Start it with `docker compose up -d llm-orchestrator` "
            "(recreate it after pulling this change, so it publishes LLM_ORCHESTRATOR_HOST_PORT)."
        ) from None
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code != 200:
        code = body.get("error", f"HTTP {response.status_code}") if isinstance(body, dict) else ""
        hints = {
            "CONTAINER_MISSING": (
                " Create the container once with `docker compose --profile vllm-embed create`."
            ),
            "OLLAMA_GPU_BUSY": (
                " Ollama models still hold the GPU 30 s after the unload request; check `ollama ps`."
            ),
            "COLIBRI_BUSY": (
                " The Colibri server on the host did not stop; see C:\\Colibri\\agent.log."
            ),
        }
        hint = hints.get(code, "")
        raise RuntimeError(f"VLLM_EMBED_ORCHESTRATOR_ERROR: {code}.{hint}")
    return body


def _status() -> dict[str, dict[str, dict[str, Any]]]:
    return _orchestrator("GET", "/status")  # type: ignore[return-value]


def _embed_state(status: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    return status["observed"][SERVICE]


# The vLLM servers of this project that hold the GPU. Ollama is left out: the orchestrator has
# its GPU models unloaded before it starts the server.
def gpu_holders(status: dict[str, dict[str, dict[str, Any]]] | None = None) -> list[str]:
    status = status or _status()
    return sorted(
        name
        for group in status.values()
        for name, item in group.items()
        if name != SERVICE and item["state"] in _RUNNING_STATES
    )


def _models_ready() -> bool:
    try:
        response = httpx.get(f"{vllm_embed_url()}/models", timeout=_PROBE_TIMEOUT)
        response.raise_for_status()
        return any(item.get("id") == DEFAULT_MODEL for item in response.json().get("data", []))
    except (httpx.HTTPError, ValueError, AttributeError):
        return False


def _wait_until_ready() -> None:
    deadline = time.monotonic() + settings.vllm_warmup_timeout_seconds
    while time.monotonic() < deadline:
        if _models_ready():
            return
        state = _embed_state(_status())
        if state["state"] not in _RUNNING_STATES:
            raise RuntimeError(
                f"VLLM_EMBED_EXITED: the server stopped while starting (state {state['state']}, "
                f"exit code {state['exitCode']}, out of memory {state['oomKilled']}); "
                "see `docker logs medicina-vllm-embed`"
            )
        time.sleep(_POLL_SECONDS)
    raise RuntimeError(
        f"VLLM_EMBED_TIMEOUT: no model after {settings.vllm_warmup_timeout_seconds} s "
        "(raise VLLM_WARMUP_TIMEOUT_SECONDS if the first start compiles the model)"
    )


@contextmanager
def running_embedding_server() -> Iterator[None]:
    """Start the server through the orchestrator, wait for the model, stop it at the end. A server
    that is already running (started by hand) is used as it is and left running."""
    status = _status()
    state = _embed_state(status)
    if state["state"] == "missing":
        raise RuntimeError(
            "VLLM_EMBED_CONTAINER_MISSING: create it once with "
            "`docker compose --profile vllm-embed create`"
        )
    if state["state"] in _RUNNING_STATES:
        _wait_until_ready()
        yield
        return
    holders = gpu_holders(status)
    if holders:
        raise RuntimeError(
            "VLLM_GPU_BUSY: the GPU is held by "
            + ", ".join(holders)
            + ". Stop them (docker stop) and run the build again."
        )
    _orchestrator("POST", f"/start/{SERVICE}")
    try:
        _wait_until_ready()
        yield
    finally:
        _orchestrator("POST", f"/stop/{SERVICE}")
