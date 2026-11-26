"""The local classifier model (message classification and condition identification) is in Ollama
only while a message needs it: loaded before its first call, released after its last.

Only in the web app with an orchestrator, where the host agent loads and releases Ollama models
(backend.ai.ollama_loading). Native runs and the scripts keep OLLAMA_KEEP_ALIVE_SECONDS.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal

from backend.ai.ollama_loading import (
    LoadResult,
    is_loaded,
    load_through_agent,
    loads_through_agent,
    release_through_agent,
)
from backend.ai.providers import LOCAL_CLASSIFIER_CONTEXT_TOKENS
from backend.config import settings
from backend.core.errors import ModelLoadRequired

logger = logging.getLogger("naturist.classification")

# The load before a message keeps the model this long at most, in case its call never comes; the
# classification keeps it as long, for a condition identification that may follow.
LOAD_KEEP_ALIVE_SECONDS = 120
# The options of the classifier's requests: another num_ctx would make Ollama load it again.
LOAD_OPTIONS = {"num_ctx": LOCAL_CLASSIFIER_CONTEXT_TOKENS}

Step = Literal["classify", "condition"]


@dataclass
class _Scope:
    ask_before_load: bool
    used: bool = False


_scope: ContextVar[_Scope | None] = ContextVar("classifier_model_scope", default=None)


def _model() -> str:
    return settings.medical_condition_ai_local_model


# One request of the chat. With ask_before_load, a classification that needs the model while
# Ollama does not hold it raises ModelLoadRequired instead of loading it unannounced; `used` says
# whether the model was called.
@contextmanager
def request_scope(*, ask_before_load: bool) -> Iterator[_Scope]:
    scope = _Scope(ask_before_load)
    token = _scope.set(scope)
    try:
        yield scope
    finally:
        _scope.reset(token)


# Called right before a request to the model.
def before_call() -> None:
    scope = _scope.get()
    if scope is None:
        return
    if scope.ask_before_load and loads_through_agent() and not loaded():
        raise ModelLoadRequired("classifier")
    scope.used = True


# The keep-alive of a request: the classification keeps the model for a condition identification
# that may follow, which then releases it. None keeps the configured one.
def keep_alive(step: Step) -> int | None:
    if not loads_through_agent():
        return None
    return LOAD_KEEP_ALIVE_SECONDS if step == "classify" else 0


def loaded() -> bool:
    return is_loaded(settings.condition_ai_local_base, _model())


# `busy` while a running report holds the memory it needs (the chat waits); `skipped` leaves the
# load to the request itself.
def load() -> LoadResult:
    return load_through_agent(
        _model(), "generate", LOAD_KEEP_ALIVE_SECONDS, dict(LOAD_OPTIONS), from_chat=True
    )


# After a classification that no condition identification follows.
def release() -> None:
    logger.info("classifier_model_release model=%s", _model())
    release_through_agent(_model())
