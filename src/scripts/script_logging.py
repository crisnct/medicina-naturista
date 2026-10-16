"""Bounded, secret-aware function-entry logging for command-line scripts."""

from __future__ import annotations

import logging
from collections.abc import Collection
from dataclasses import fields, is_dataclass
from functools import wraps
from inspect import signature
from reprlib import Repr

_REPR = Repr()
_REPR.maxstring = 200
_REPR.maxother = 200


def _parameter(name, value):
    if any(secret in name.lower() for secret in ("password", "token", "secret")):
        return "<redacted>"
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _parameter(field.name, getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Collection) and not isinstance(value, (str, bytes)):
        return f"{type(value).__name__}(len={len(value)})"
    return _REPR.repr(value)


def log_call(function):
    """Log every supplied/default parameter only when DEBUG tracing is enabled."""
    logger = logging.getLogger(function.__module__)
    parameters = signature(function)

    @wraps(function)
    def call(*args, **kwargs):
        if logger.isEnabledFor(logging.DEBUG):
            try:
                bound = parameters.bind(*args, **kwargs)
                bound.apply_defaults()
                values = {name: _parameter(name, value) for name, value in bound.arguments.items()}
                logger.debug("start %s parameters=%s", function.__qualname__, values)
            except Exception:
                # Diagnostics must never prevent the operation being diagnosed.
                logger.debug("start %s parameters=<unavailable>", function.__qualname__)
        return function(*args, **kwargs)

    return call
