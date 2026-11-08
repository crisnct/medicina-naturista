"""Brings the GPU to the state a report model needs before the job sends its first request.

The state is always read from Docker, so it survives app restarts and manual commands. Called only
from the single report worker, outside every lock, so nothing else uses a model while it changes.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from backend.ai.providers import LOCAL_HOSTS
from backend.config import Settings
from backend.core.contracts import ModelStage
from backend.core.errors import ApplicationError
from backend.core.report_models import REPORT_MODELS, ReportModel
from backend.core.texts import tr

logger = logging.getLogger("naturist.reports")

_POLL_SECONDS = 2.0
_SUPERVISOR_TIMEOUT = httpx.Timeout(90.0, connect=5.0)
_PROBE_TIMEOUT = httpx.Timeout(3.0, connect=2.0)
_OLLAMA_UNLOAD_SECONDS = 30.0
_RUNNING_STATES = frozenset({"running", "restarting"})


class _SupervisorUnavailable(Exception):
    pass


class VllmRuntime:
    def __init__(
        self,
        settings: Settings,
        *,
        http: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._supervisor = settings.model_supervisor_url
        self._vllm_base = settings.vllm_api_base
        self._ollama_base = settings.ollama_api_base.removesuffix("/v1")
        self._ollama_local = (httpx.URL(self._ollama_base).host or "") in LOCAL_HOSTS
        self._warmup_seconds = settings.vllm_warmup_timeout_seconds
        self._http = http or httpx.Client()
        self._clock = clock
        self._sleep = sleep
        # Kept in memory only: after an app restart the first local report releases the GPU once.
        self._last_local_model: ReportModel | None = None

    def close(self) -> None:
        self._http.close()

    def prepare(
        self,
        model: ReportModel,
        on_stage: Callable[[ModelStage], None],
        checkpoint: Callable[[], None],
    ) -> None:
        spec = REPORT_MODELS[model]
        # A cloud report leaves the GPU alone, so returning to a running vLLM model stays instant.
        # A local report with a model other than the previous local report's frees the GPU first:
        # every Ollama model is unloaded, and the vLLM containers are stopped below (all but the
        # chosen vLLM model's own). Repeating the same model releases nothing.
        local = spec.provider in ("ollama", "vllm")
        if local and model != self._last_local_model:
            self._unload_ollama()
        if spec.provider == "ollama":
            self._prepare_ollama(on_stage)
        elif spec.provider == "vllm":
            if spec.vllm_service is None:
                raise ValueError(f"The vLLM model {model} names no Compose service")
            self._prepare_vllm(spec.vllm_service, spec.model, on_stage, checkpoint)
        if local:
            self._last_local_model = model

    # Without the supervisor nothing can be stopped, but Ollama itself still answers: the report
    # may run slower beside a vLLM server, which beats refusing every local report.
    def _prepare_ollama(self, on_stage: Callable[[ModelStage], None]) -> None:
        try:
            status = self._status()
        except _SupervisorUnavailable:
            logger.warning("model_supervisor_unavailable target=ollama")
            return
        self._stop_running(status, None, on_stage)

    def _prepare_vllm(
        self,
        service: str,
        served_model: str,
        on_stage: Callable[[ModelStage], None],
        checkpoint: Callable[[], None],
    ) -> None:
        try:
            status = self._status()
        except _SupervisorUnavailable:
            raise ApplicationError(
                "MODEL_SUPERVISOR_UNAVAILABLE", tr("errors.model_supervisor_unavailable"), 503
            )
        if any(item["state"] in _RUNNING_STATES for item in status["observed"].values()):
            raise ApplicationError("VLLM_GPU_BUSY", tr("errors.vllm_gpu_busy"), 409)
        state = status["managed"].get(service, {}).get("state")
        if state == "missing" or state is None:
            raise ApplicationError(
                "VLLM_CONTAINER_MISSING", tr("errors.vllm_container_missing"), 503
            )
        self._stop_running(status, service, on_stage)
        if state in _RUNNING_STATES:
            if self._serves(served_model):
                return
            on_stage("warming_model")
        else:
            on_stage("warming_model")
            self._start(service)
        self._wait_ready(service, served_model, checkpoint)

    def _status(self) -> dict[str, dict[str, dict[str, Any]]]:
        try:
            response = self._http.get(f"{self._supervisor}/status", timeout=_SUPERVISOR_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("model_supervisor_status_failed type=%s", type(exc).__name__)
            raise _SupervisorUnavailable from None

    def _stop_running(
        self,
        status: dict[str, dict[str, dict[str, Any]]],
        keep: str | None,
        on_stage: Callable[[ModelStage], None],
    ) -> None:
        for service, item in status["managed"].items():
            if service != keep and item["state"] in _RUNNING_STATES:
                on_stage("stopping_model")
                self._stop(service)

    def _stop(self, service: str) -> None:
        started = self._clock()
        try:
            response = self._http.post(
                f"{self._supervisor}/stop/{service}", timeout=_SUPERVISOR_TIMEOUT
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("vllm_stop_failed service=%s type=%s", service, type(exc).__name__)
            raise ApplicationError("VLLM_STOP_FAILED", tr("errors.vllm_stop_failed"), 503) from None
        logger.info(
            "vllm_stopped service=%s duration_ms=%s",
            service,
            round((self._clock() - started) * 1000),
        )

    def _start(self, service: str) -> None:
        try:
            response = self._http.post(
                f"{self._supervisor}/start/{service}", timeout=_SUPERVISOR_TIMEOUT
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("vllm_start_failed service=%s type=%s", service, type(exc).__name__)
            raise ApplicationError(
                "VLLM_START_FAILED", tr("errors.vllm_start_failed"), 503
            ) from None
        logger.info("vllm_starting service=%s", service)

    # A model held on the GPU keeps vLLM from allocating its share (it exits on startup), and
    # OLLAMA_KEEP_ALIVE_SECONDS can hold one for a long time. If this fails the report's own
    # request is what the user sees, so a problem here is only logged.
    def _unload_ollama(self) -> None:
        if not self._ollama_local:
            return
        try:
            for model in self._ollama_loaded():
                self._http.post(
                    f"{self._ollama_base}/api/generate",
                    json={"model": model, "keep_alive": 0},
                    timeout=_SUPERVISOR_TIMEOUT,
                ).raise_for_status()
            deadline = self._clock() + _OLLAMA_UNLOAD_SECONDS
            while self._ollama_loaded():
                if self._clock() >= deadline:
                    logger.warning("ollama_unload_incomplete")
                    return
                self._sleep(_POLL_SECONDS)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            logger.warning("ollama_unload_failed type=%s", type(exc).__name__)

    def _ollama_loaded(self) -> list[str]:
        response = self._http.get(f"{self._ollama_base}/api/ps", timeout=_PROBE_TIMEOUT)
        response.raise_for_status()
        return [item["name"] for item in response.json().get("models") or []]

    def _wait_ready(self, service: str, served_model: str, checkpoint: Callable[[], None]) -> None:
        started = self._clock()
        while True:
            checkpoint()
            if self._serves(served_model):
                logger.info(
                    "vllm_ready service=%s duration_ms=%s",
                    service,
                    round((self._clock() - started) * 1000),
                )
                return
            try:
                item = self._status()["managed"].get(service, {})
            except _SupervisorUnavailable:
                raise ApplicationError(
                    "MODEL_SUPERVISOR_UNAVAILABLE", tr("errors.model_supervisor_unavailable"), 503
                )
            if item.get("state") not in _RUNNING_STATES:
                logger.error(
                    "vllm_exited_during_warmup service=%s exit_code=%s oom=%s",
                    service,
                    item.get("exitCode"),
                    item.get("oomKilled"),
                )
                raise ApplicationError("VLLM_START_FAILED", tr("errors.vllm_start_failed"), 503)
            if self._clock() - started >= self._warmup_seconds:
                logger.error("vllm_warmup_timeout service=%s", service)
                raise ApplicationError("VLLM_WARMUP_TIMEOUT", tr("errors.vllm_warmup_timeout"), 504)
            self._sleep(_POLL_SECONDS)

    # A running container is not enough: the weights load after it starts. Naming the model also
    # proves that the right server answered on the address the report servers share.
    def _serves(self, served_model: str) -> bool:
        try:
            response = self._http.get(f"{self._vllm_base}/models", timeout=_PROBE_TIMEOUT)
            response.raise_for_status()
            return any(item.get("id") == served_model for item in response.json().get("data", []))
        except (httpx.HTTPError, ValueError, AttributeError):
            return False
