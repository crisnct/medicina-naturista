"""Loads of the app's local Ollama models go through the LLM host agent, so Colibri's model leaves
first and an Ollama model never loads beside it.

The web app registers the loader at startup when it has an llm-orchestrator (VllmRuntime relays
the load to the agent). Without one (native runs, the scripts) nothing is registered and Ollama
loads a model on its first request, as before.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Literal

import httpx

from backend.ai.providers import LOCAL_HOSTS

logger = logging.getLogger("naturist.ollama_loading")

# `busy`: a load for the chat would push out a model a running report (or vllm-embed,
# vllm-translate) uses, so the chat waits; `skipped`: no agent load (none registered, a Colibri
# report running, or the agent failed), so the request itself loads the model.
LoadResult = Literal["loaded", "busy", "skipped"]
# model, api ("embed" or "generate"), keep_alive, options, for the chat -> the outcome.
Loader = Callable[[str, str, int | str | None, dict[str, Any], bool], LoadResult]
# model -> nothing: the agent has Ollama unload that one model.
Releaser = Callable[[str], None]

_PS_TIMEOUT = httpx.Timeout(2.0, connect=1.0)
_loader: Loader | None = None
_releaser: Releaser | None = None


def use_loader(loader: Loader | None, releaser: Releaser | None = None) -> None:
    global _loader, _releaser
    _loader = loader
    _releaser = releaser


# True in the web app with an orchestrator: the agent loads the models, so a model the app uses
# for one message only (the classifier) may leave Ollama right after it.
def loads_through_agent() -> bool:
    return _loader is not None


# A load for the chat (from_chat) may answer `busy`; the report's and the requests' own loads never
# wait.
def load_through_agent(
    model: str,
    api: str,
    keep_alive: int | str | None,
    options: dict[str, Any],
    *,
    from_chat: bool = False,
) -> LoadResult:
    if _loader is None:
        return "skipped"
    return _loader(model, api, keep_alive, options, from_chat)


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
    if is_loaded(base, model):
        return
    if _loader(model, api, keep_alive, options, False) != "loaded":
        logger.info("ollama_load_left_to_request model=%s", model)


# Where the Ollama at `base_url` holds `model`: (in RAM, in VRAM); None when it does not hold it or
# does not answer.
def placement(base_url: str, model: str) -> tuple[bool, bool] | None:
    try:
        response = httpx.get(f"{base_url.removesuffix('/v1')}/api/ps", timeout=_PS_TIMEOUT)
        response.raise_for_status()
        for item in response.json().get("models") or []:
            if model in (item.get("name"), item.get("model")):
                size, vram = int(item.get("size") or 0), int(item.get("size_vram") or 0)
                return size > vram, vram > 0
    except (httpx.HTTPError, ValueError, AttributeError, TypeError):
        return None
    return None


# Whether the Ollama at `base_url` holds `model`. Reading /api/ps changes nothing; an Ollama that
# does not answer holds no model.
def is_loaded(base_url: str, model: str) -> bool:
    try:
        response = httpx.get(f"{base_url.removesuffix('/v1')}/api/ps", timeout=_PS_TIMEOUT)
        response.raise_for_status()
        return any(
            model in (item.get("name"), item.get("model"))
            for item in response.json().get("models") or []
        )
    except (httpx.HTTPError, ValueError, AttributeError):
        return False


# Has the agent unload `model` from Ollama; nothing without an agent (native runs, the scripts).
def release_through_agent(model: str) -> None:
    if _releaser is not None:
        _releaser(model)
