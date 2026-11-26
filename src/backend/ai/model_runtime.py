"""Brings the GPU to the state a report model needs before the job sends its first request.

The state is always read from Docker and from the LLM host agent, both through the
llm-orchestrator, so it survives app restarts
and manual commands. Called only from the single report worker, outside every lock, so nothing else
uses a model while it changes.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, cast

import httpx

from backend.ai.ollama_loading import LoadResult, placement
from backend.ai.providers import LOCAL_HOSTS
from backend.config import Settings
from backend.core.contracts import ConfirmResources, ModelStage, ResourceCheck
from backend.core.errors import ApplicationError
from backend.core.report_models import (
    COLIBRI_RECOMMENDED_RAM_GB,
    COLIBRI_RECOMMENDED_VRAM_GB,
    REPORT_MODELS,
    ReportModel,
)
from backend.core.texts import tr

logger = logging.getLogger("naturist.reports")

_POLL_SECONDS = 2.0
# A start may first stop a loaded Colibri through the host agent (up to 120 s) and unload Ollama
# through it (up to 60 s).
_ORCHESTRATOR_TIMEOUT = httpx.Timeout(240.0, connect=5.0)
_PROBE_TIMEOUT = httpx.Timeout(3.0, connect=2.0)
_RUNNING_STATES = frozenset({"running", "restarting"})
# The host agent's calls go through the orchestrator, which gives each up to 330 s (`coli plan`
# reads the model's layout from disk; a stop waits for the engine to exit; a load may stop Colibri,
# start Ollama and read a model from disk) and may first wait for another change to finish.
_AGENT_TIMEOUT = httpx.Timeout(420.0, connect=5.0)
# Loading takes seconds when the files are in the page cache, longer from a cold disk.
_COLIBRI_WARMUP_SECONDS = 600.0


class _OrchestratorUnavailable(Exception):
    pass


# The level of the agent's memory test: the planner's refusal blocks, memory below what the speed
# was measured with only warns.
def resource_check(reply: dict[str, Any]) -> ResourceCheck:
    ram = reply.get("ramAvailableGb")
    vram = reply.get("vramFreeGb")
    valid = bool(reply.get("planValid"))
    comfortable = (
        isinstance(ram, (int, float))
        and ram >= COLIBRI_RECOMMENDED_RAM_GB
        and isinstance(vram, (int, float))
        and vram >= COLIBRI_RECOMMENDED_VRAM_GB
    )
    warnings = reply.get("planWarnings")
    return {
        "level": "blocking" if not valid else "ok" if comfortable else "warning",
        "ramAvailableGb": ram if isinstance(ram, (int, float)) else None,
        "ramMinimumGb": reply.get("ramMinimumGb"),
        "ramRecommendedGb": COLIBRI_RECOMMENDED_RAM_GB,
        "vramFreeGb": vram if isinstance(vram, (int, float)) else None,
        "vramRecommendedGb": COLIBRI_RECOMMENDED_VRAM_GB,
        "planValid": valid,
        "planWarnings": [str(item)[:300] for item in warnings][:8]
        if isinstance(warnings, list)
        else [],
        "expertsPerLayer": reply.get("expertsPerLayer"),
        "expertResidencyPct": reply.get("expertResidencyPct"),
    }


def _error_code(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    return body.get("error") if isinstance(body, dict) else None


class VllmRuntime:
    def __init__(
        self,
        settings: Settings,
        *,
        http: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._orchestrator = settings.llm_orchestrator_url
        self._vllm_base = settings.vllm_api_base
        self._colibri_base = settings.colibri_api_base
        # Only an Ollama of this machine shares the GPU; the host agent manages that one.
        self._ollama_local = (httpx.URL(settings.ollama_api_base).host or "") in LOCAL_HOSTS
        self._warmup_seconds = settings.vllm_warmup_timeout_seconds
        self._http = http or httpx.Client()
        self._clock = clock
        self._sleep = sleep
        # Kept in memory only: after an app restart the first local report releases the GPU once.
        self._last_local_model: ReportModel | None = None
        # Ollama ran before a Colibri report stopped it, so finish() starts it again.
        self._restart_ollama = False
        # From a Colibri report's prepare() to its finish(): Ollama is stopped on purpose, and no
        # load may start it again (read by the web threads, written by the report worker).
        self._colibri_report_running = False
        # From a local Ollama or vLLM report's prepare() to its finish(): its model is in use, so no
        # load pushes it out and the chat's loads into its memory wait (read by the web threads).
        self._active_report: ReportModel | None = None
        self._ollama_base = settings.ollama_api_base

    def close(self) -> None:
        self._http.close()

    # Every local Ollama model the app uses is loaded by the host agent, through the orchestrator
    # (registered in backend.ai.ollama_loading): Colibri's model leaves first, and a stopped Ollama
    # is started. Never while a Colibri report runs, whose finish() starts Ollama again: then the
    # caller's own request loads the model, as before.
    #
    # One model per memory. A model with num_gpu 0 goes to RAM, any other to VRAM first; the agent
    # pushes out the Ollama models in that memory (and, when the new one spills into RAM, those in
    # RAM), and before a VRAM load the idle vLLM report server stops here. A model in use is never
    # pushed out: the running report's Ollama model is protected, and a load for the chat into
    # memory a running report, vllm-embed or vllm-translate holds answers `busy` instead.
    def load_ollama_model(
        self,
        model: str,
        api: str,
        keep_alive: int | str | None,
        options: dict[str, Any],
        from_chat: bool = False,
    ) -> LoadResult:
        if not self._ollama_local or self._colibri_report_running:
            return "skipped"
        on_cpu = options.get("num_gpu") == 0
        try:
            status: dict[str, dict[str, dict[str, Any]]] | None = self._status()
        except _OrchestratorUnavailable:
            status = None
        if from_chat and self.load_busy(on_cpu, status):
            logger.info("ollama_load_waits model=%s on_cpu=%s", model, on_cpu)
            return "busy"
        active = self._active_report
        if not on_cpu and status is not None:
            in_use = REPORT_MODELS[active].vllm_service if active is not None else None
            for service, item in status["managed"].items():
                if item.get("state") in _RUNNING_STATES and service != in_use:
                    try:
                        self._stop(service)
                    except ApplicationError:
                        logger.warning("vllm_stop_before_ollama_failed service=%s", service)
        protect = (
            [REPORT_MODELS[active].model]
            if active is not None and REPORT_MODELS[active].provider == "ollama"
            else []
        )
        try:
            self._agent(
                "POST",
                "/ollama/load",
                {
                    "model": model,
                    "api": api,
                    "keepAlive": keep_alive,
                    "options": options,
                    "protect": protect,
                },
            )
        except ApplicationError as exc:
            logger.warning("ollama_load_failed model=%s code=%s", model, exc.code)
            return "skipped"
        logger.info("ollama_loaded_through_agent model=%s", model)
        return "loaded"

    # Whether a chat load into RAM (on_cpu) or VRAM would push out a model in use: the running local
    # report's (an Ollama model where /api/ps shows it, VRAM while it is not loaded yet; a vLLM one
    # in VRAM), or a running vllm-embed or vllm-translate (VRAM; the app cannot tell whether they
    # work, so they count as in use). A Colibri report is not counted: no load runs during it.
    def load_busy(
        self, on_cpu: bool, status: dict[str, dict[str, dict[str, Any]]] | None = None
    ) -> bool:
        active = self._active_report
        if active is not None:
            spec = REPORT_MODELS[active]
            if spec.provider == "vllm" and not on_cpu:
                return True
            if spec.provider == "ollama":
                in_ram, in_vram = placement(self._ollama_base, spec.model) or (False, True)
                if in_ram if on_cpu else in_vram:
                    return True
        if on_cpu:
            return False
        if status is None:
            try:
                status = self._status()
            except _OrchestratorUnavailable:
                return False
        return any(item.get("state") in _RUNNING_STATES for item in status["observed"].values())

    # The admin's unload from the window of loaded models, whatever uses the model: an Ollama model
    # leaves once its running requests end (keep_alive 0; Ollama stays up), a vLLM server stops
    # (a report or index build using it fails), Colibri stops gracefully. `ident` is the window's
    # id: the Ollama model, the Compose service, or "colibri".
    def unload_local_model(self, runtime: str, ident: str) -> None:
        if runtime == "ollama":
            self._agent("POST", "/ollama/release", {"model": ident})
        elif runtime == "vllm":
            self._stop(ident)
        elif runtime == "colibri":
            self._agent("POST", "/stop")
        else:
            raise ValueError(f"Unknown runtime {runtime!r}")
        logger.info("local_model_unloaded runtime=%s model=%s", runtime, ident)

    # The release of one Ollama model (the classifier after a message), through the host agent.
    # Never while a Colibri report runs, which keeps Ollama stopped; a failure only logs, since
    # the model then leaves at the end of its keep-alive.
    def release_ollama_model(self, model: str) -> None:
        if not self._ollama_local or self._colibri_report_running:
            return
        try:
            self._agent("POST", "/ollama/release", {"model": model})
        except ApplicationError as exc:
            logger.warning("ollama_release_failed model=%s code=%s", model, exc.code)
            return
        logger.info("ollama_released_through_agent model=%s", model)

    def prepare(
        self,
        model: ReportModel,
        on_stage: Callable[[ModelStage], None],
        checkpoint: Callable[[], None],
        confirm: ConfirmResources | None = None,
    ) -> None:
        spec = REPORT_MODELS[model]
        if spec.provider in ("ollama", "vllm"):
            self._active_report = model
        # Colibri stays loaded until a report with any other model, cloud ones included.
        if spec.provider == "colibri":
            self._colibri_report_running = True
            self._prepare_colibri(spec.model, on_stage, checkpoint, confirm)
            self._last_local_model = model
            return
        self._stop_colibri(on_stage)
        # A cloud report leaves the GPU alone, so returning to a running vLLM model stays instant.
        # A local report with a model other than the previous local report's frees the GPU first:
        # the vLLM containers are stopped below (all but the chosen vLLM model's own), and the host
        # agent unloads the Ollama models, asked here for an Ollama report and by the orchestrator
        # before it starts a vLLM container. Repeating the same model releases nothing.
        local = spec.provider in ("ollama", "vllm")
        if spec.provider == "ollama" and model != self._last_local_model:
            self._unload_ollama()
        if spec.provider == "ollama":
            self._prepare_ollama(on_stage)
        elif spec.provider == "vllm":
            if spec.vllm_service is None:
                raise ValueError(f"The vLLM model {model} names no Compose service")
            self._prepare_vllm(spec.vllm_service, spec.model, on_stage, checkpoint)
        if local:
            self._last_local_model = model

    # Without the orchestrator nothing can be stopped, but Ollama itself still answers: the report
    # may run slower beside a vLLM server, which beats refusing every local report.
    def _prepare_ollama(self, on_stage: Callable[[ModelStage], None]) -> None:
        try:
            status = self._status()
        except _OrchestratorUnavailable:
            logger.warning("llm_orchestrator_unavailable target=ollama")
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
        except _OrchestratorUnavailable:
            raise ApplicationError(
                "LLM_ORCHESTRATOR_UNAVAILABLE", tr("errors.llm_orchestrator_unavailable"), 503
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
            response = self._http.get(f"{self._orchestrator}/status", timeout=_ORCHESTRATOR_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("llm_orchestrator_status_failed type=%s", type(exc).__name__)
            raise _OrchestratorUnavailable from None

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
                f"{self._orchestrator}/stop/{service}", timeout=_ORCHESTRATOR_TIMEOUT
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
                f"{self._orchestrator}/start/{service}", timeout=_ORCHESTRATOR_TIMEOUT
            )
            # The host agent could not unload the Ollama models that hold the GPU.
            if response.status_code == 409 and _error_code(response) == "OLLAMA_GPU_BUSY":
                logger.error("vllm_start_refused service=%s reason=ollama_gpu_busy", service)
                raise ApplicationError("VLLM_GPU_BUSY", tr("errors.vllm_gpu_busy"), 409)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("vllm_start_failed service=%s type=%s", service, type(exc).__name__)
            raise ApplicationError(
                "VLLM_START_FAILED", tr("errors.vllm_start_failed"), 503
            ) from None
        logger.info("vllm_starting service=%s", service)

    # The host agent unloads the Ollama models that hold GPU memory: OLLAMA_KEEP_ALIVE_SECONDS can
    # keep one there for a long time. The model that embeds questions runs on the CPU and stays,
    # unless every_model asks for it too: Colibri needs its RAM. The app asks through the
    # orchestrator and never calls Ollama's admin API itself. Without an agent nothing is unloaded,
    # and if this fails the report's own request is what the user sees, so a problem here is only
    # logged.
    def _unload_ollama(self, *, every_model: bool = False) -> None:
        if not self._ollama_local:
            return
        try:
            reply = self._agent("POST", "/ollama/unload?all=1" if every_model else "/ollama/unload")
        except ApplicationError as exc:
            logger.warning("ollama_unload_failed code=%s", exc.code)
            return
        logger.info("ollama_unloaded every_model=%s state=%s", every_model, reply.get("state"))

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
            except _OrchestratorUnavailable:
                raise ApplicationError(
                    "LLM_ORCHESTRATOR_UNAVAILABLE", tr("errors.llm_orchestrator_unavailable"), 503
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

    # Every vLLM server and every Ollama model (the question embedder too) leave first; then the
    # agent measures the memory, and below the thresholds the user decides. A server that already
    # answers keeps running: it holds its memory, so measuring again would only scare the user.
    def _prepare_colibri(
        self,
        served_model: str,
        on_stage: Callable[[ModelStage], None],
        checkpoint: Callable[[], None],
        confirm: ConfirmResources | None,
    ) -> None:
        on_stage("stopping_model")
        # Even beside a loaded Colibri: a search since the last report may have loaded the question
        # embedder again, and its RAM is what the experts need.
        self._stop_ollama()
        if self._colibri_serves(served_model):
            return
        try:
            status = self._status()
        except _OrchestratorUnavailable:
            logger.warning("llm_orchestrator_unavailable target=colibri")
        else:
            if any(item["state"] in _RUNNING_STATES for item in status["observed"].values()):
                raise ApplicationError("VLLM_GPU_BUSY", tr("errors.vllm_gpu_busy"), 409)
            self._stop_running(status, None, on_stage)
        while True:
            checkpoint()
            on_stage("checking_resources")
            check = resource_check(self._agent("POST", "/check"))
            logger.info(
                "colibri_resources_checked level=%s ram_available_gb=%s vram_free_gb=%s",
                check["level"],
                check["ramAvailableGb"],
                check["vramFreeGb"],
            )
            if check["level"] == "ok":
                break
            if confirm is None:
                if check["level"] == "blocking":
                    raise ApplicationError(
                        "COLIBRI_RESOURCES_INSUFFICIENT",
                        tr("errors.colibri_resources_insufficient"),
                        409,
                    )
                break
            # "continue" cannot start a server the planner refuses, so it measures again.
            if confirm(check) == "continue" and check["level"] == "warning":
                break
        checkpoint()
        on_stage("warming_model")
        self._agent("POST", "/start")
        self._wait_colibri(served_model, checkpoint)

    def _wait_colibri(self, served_model: str, checkpoint: Callable[[], None]) -> None:
        started = self._clock()
        while True:
            checkpoint()
            if self._colibri_serves(served_model):
                logger.info("colibri_ready duration_ms=%s", round((self._clock() - started) * 1000))
                return
            if not self._agent("GET", "/status").get("running"):
                logger.error("colibri_exited_during_warmup")
                raise ApplicationError(
                    "COLIBRI_START_FAILED", tr("errors.colibri_start_failed"), 503
                )
            if self._clock() - started >= _COLIBRI_WARMUP_SECONDS:
                logger.error("colibri_warmup_timeout")
                raise ApplicationError(
                    "COLIBRI_WARMUP_TIMEOUT", tr("errors.colibri_warmup_timeout"), 504
                )
            self._sleep(_POLL_SECONDS)

    # The whole Ollama process tree leaves, not only its models: the server, its runners and the
    # tray app hold RAM too. Search and message classification are unavailable until finish().
    def _stop_ollama(self) -> None:
        if not self._ollama_local:
            return
        try:
            reply = self._agent("POST", "/ollama/stop")
        except ApplicationError as exc:
            # When the process cannot be stopped, unloading every model still frees most of that
            # memory.
            logger.warning("ollama_stop_failed code=%s fallback=unload", exc.code)
            self._unload_ollama(every_model=True)
            return
        self._restart_ollama = self._restart_ollama or bool(reply.get("wasRunning"))
        logger.info("ollama_stopped_for_colibri was_running=%s", reply.get("wasRunning"))

    def finish(self, model: ReportModel) -> None:
        if self._active_report == model:
            self._active_report = None
        if REPORT_MODELS[model].provider != "colibri":
            return
        self._colibri_report_running = False
        if not self._restart_ollama:
            return
        try:
            self._agent("POST", "/ollama/start")
        except ApplicationError as exc:
            logger.error("ollama_restart_failed code=%s", exc.code)
            return
        self._restart_ollama = False
        logger.info("ollama_restarted_after_colibri")

    # Any other report frees Colibri's memory first. Without an agent there is nothing to stop,
    # and an agent that does not answer must not block a report with another model.
    def _stop_colibri(self, on_stage: Callable[[ModelStage], None]) -> None:
        try:
            if not self._agent("GET", "/status").get("running"):
                return
            on_stage("stopping_model")
            self._agent("POST", "/stop")
            logger.info("colibri_stopped")
        except ApplicationError as exc:
            logger.warning("colibri_stop_skipped code=%s", exc.code)

    def _colibri_serves(self, served_model: str) -> bool:
        try:
            response = self._http.get(f"{self._colibri_base}/models", timeout=_PROBE_TIMEOUT)
            response.raise_for_status()
            return any(item.get("id") == served_model for item in response.json().get("data", []))
        except (httpx.HTTPError, ValueError, AttributeError):
            return False

    # The app never calls the host agent itself: the orchestrator relays these calls, so an
    # orchestrator that does not answer is LLM_ORCHESTRATOR_UNAVAILABLE, and an agent that is not
    # configured or does not answer is LLM_HOST_AGENT_UNAVAILABLE.
    def _agent(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            response = self._http.request(
                method,
                f"{self._orchestrator}/host-agent{path}",
                json=payload,
                timeout=_AGENT_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            logger.error("host_agent_relay_failed path=%s type=%s", path, type(exc).__name__)
            raise ApplicationError(
                "LLM_ORCHESTRATOR_UNAVAILABLE", tr("errors.llm_orchestrator_unavailable"), 503
            ) from None
        code = _error_code(response)
        if code == "HOST_AGENT_UNAVAILABLE":
            logger.warning("host_agent_unavailable path=%s", path)
            raise ApplicationError(
                "LLM_HOST_AGENT_UNAVAILABLE", tr("errors.llm_host_agent_unavailable"), 503
            )
        if response.status_code == 409 and code == "INSUFFICIENT_RESOURCES":
            raise ApplicationError(
                "COLIBRI_RESOURCES_INSUFFICIENT", tr("errors.colibri_resources_insufficient"), 409
            )
        if response.status_code >= 400:
            logger.error(
                "host_agent_refused path=%s status=%s code=%s", path, response.status_code, code
            )
            if path == "/start":
                raise ApplicationError(
                    "COLIBRI_START_FAILED", tr("errors.colibri_start_failed"), 503
                )
            raise ApplicationError(
                "LLM_HOST_AGENT_UNAVAILABLE", tr("errors.llm_host_agent_unavailable"), 503
            )
        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise ApplicationError(
                "LLM_HOST_AGENT_UNAVAILABLE", tr("errors.llm_host_agent_unavailable"), 503
            )
        return cast(dict[str, Any], body)
