"""Loads of the app's local Ollama models go through the LLM host agent, so Colibri's model leaves
first and an Ollama model never loads beside it.

The web app registers the loader at startup when it has an llm-orchestrator (VllmRuntime relays
the load to the agent). Without one (native runs, the scripts) nothing is registered and Ollama
loads a model on its first request, as before.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import httpx

from backend.ai.providers import LOCAL_HOSTS

logger = logging.getLogger("naturist.ollama_loading")

# model, api ("embed" or "generate"), keep_alive, options -> whether the agent loaded it.
Loader = Callable[[str, str, int | str | None, dict[str, Any]], bool]

_PS_TIMEOUT = httpx.Timeout(2.0, connect=1.0)
_loader: Loader | None = None


def use_loader(loader: Loader | None) -> None:
    global _loader
    _loader = loader


# True in the web app with an orchestrator: the agent loads the models, so a model the app uses
# for one question only (the question embedder) may leave Ollama right after it.
def loads_through_agent() -> bool:
    return _loader is not None


# Says whether the agent loaded the model; False leaves the load to the caller's own request.
def load_through_agent(
    model: str, api: str, keep_alive: int | str | None, options: dict[str, Any]
) -> bool:
    return _loader is not None and _loader(model, api, keep_alive, options)


# Before a request to a local Ollama: a model it does not hold is loaded by the agent first, with
# the options the request uses (another num_ctx would make Ollama load it again). Reading
# /api/ps changes nothing; a stopped Ollama answers nothing, and the agent starts it.
def ensure_loaded(
    base_url: str,
    model: str,
    *,
    api: str,
    keep_alive: int | str | None,
    options: dict[str, Any],
) -> None:
    if _loader is None:
        return
    base = base_url.removesuffix("/v1")
    if (httpx.URL(base).host or "") not in LOCAL_HOSTS:
        return
    try:
        response = httpx.get(f"{base}/api/ps", timeout=_PS_TIMEOUT)
        response.raise_for_status()
        if any(
            model in (item.get("name"), item.get("model"))
            for item in response.json().get("models") or []
        ):
            return
    except (httpx.HTTPError, ValueError, AttributeError):
        pass
    if not _loader(model, api, keep_alive, options):
        logger.info("ollama_load_left_to_request model=%s", model)
