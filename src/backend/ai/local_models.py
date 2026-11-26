"""The local AI models in memory right now and where they sit (RAM, VRAM), for the chat's window.

Read through the llm-orchestrator only (Docker's state, and the LLM host agent for Ollama and
Colibri), never by changing anything, and cached for a few seconds: any number of visitors cost
one read per interval.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx

from backend.ai.embedding_model import DEFAULT_MODEL, is_query_model
from backend.config import Settings
from backend.core.contracts import LocalModel, LocalModelRole, LocalModelsState
from backend.core.report_models import REPORT_MODELS

logger = logging.getLogger("naturist.ai")

# The chat asks every 3 s while its tab is visible; one read serves every visitor in that time.
CACHE_SECONDS = 3.0
_RELAY_TIMEOUT = httpx.Timeout(4.0, connect=2.0)
# A vLLM server answers /health only once its weights are loaded.
_HEALTH_TIMEOUT = httpx.Timeout(1.0, connect=1.0)
_RUNNING_STATES = frozenset({"running", "restarting"})
# Every vLLM container listens on 8000 inside the Compose network, under its service name.
_VLLM_HEALTH_URL = "http://{service}:8000/health"
# The vLLM servers that are not report models, by Compose service: what they serve and why.
_VLLM_OTHERS: dict[str, tuple[str, LocalModelRole]] = {
    "vllm-embed": (DEFAULT_MODEL, "index_embedding"),
    "vllm-translate": ("translategemma", "translation"),
}
_UNAVAILABLE: LocalModelsState = {"available": False, "partial": False, "models": []}


# Ollama names a model without a tag `<name>:latest`.
def _tagged(name: str) -> str:
    return name if ":" in name.rsplit("/", 1)[-1] else f"{name}:latest"


def _split(ram: float, vram: float) -> tuple[int | None, int | None]:
    total = ram + vram
    if total <= 0:
        return None, None
    vram_pct = round(100 * vram / total)
    return 100 - vram_pct, vram_pct


class LocalModels:
    def __init__(
        self,
        settings: Settings,
        *,
        http: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._orchestrator = settings.llm_orchestrator_url
        self._classifier = _tagged(settings.medical_condition_ai_local_model)
        self._http = http or httpx.Client()
        self._clock = clock
        # Held for the whole read, so the requests that arrive meanwhile wait and reuse its result.
        self._lock = threading.Lock()
        self._cached: LocalModelsState | None = None
        self._cached_at = 0.0

    def close(self) -> None:
        self._http.close()

    # After an unload: the next read sees the change at once.
    def invalidate(self) -> None:
        with self._lock:
            self._cached = None

    def __call__(self) -> LocalModelsState:
        with self._lock:
            if self._cached is None or self._clock() - self._cached_at >= CACHE_SECONDS:
                self._cached = self._read()
                self._cached_at = self._clock()
            return self._cached

    def _read(self) -> LocalModelsState:
        if not self._orchestrator:
            return _UNAVAILABLE
        status = self._get("/status")
        agent = self._get("/host-agent/models")
        if status is None and agent is None:
            return _UNAVAILABLE
        models: list[LocalModel] = []
        if agent is not None:
            models.extend(self._ollama(agent.get("ollama")))
        if status is not None:
            models.extend(self._vllm(status))
        if agent is not None:
            models.extend(self._colibri(agent.get("colibri")))
        return {
            "available": True,
            "partial": status is None or agent is None,
            "models": models,
        }

    def _get(self, path: str) -> dict[str, Any] | None:
        try:
            response = self._http.get(f"{self._orchestrator}{path}", timeout=_RELAY_TIMEOUT)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("local_models_read_failed path=%s type=%s", path, type(exc).__name__)
            return None
        return body if isinstance(body, dict) else None

    def _ollama_roles(self, name: str) -> list[LocalModelRole]:
        tagged = _tagged(name)
        roles: list[LocalModelRole] = []
        if is_query_model(name) or is_query_model(tagged):
            roles.append("query_embedding")
        if tagged == self._classifier:
            roles.append("classifier")
        if any(
            spec.provider == "ollama" and _tagged(spec.model) == tagged
            for spec in REPORT_MODELS.values()
        ):
            roles.append("report")
        return roles or ["unknown"]

    def _ollama(self, items: Any) -> list[LocalModel]:
        models: list[LocalModel] = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue
            size = item.get("size")
            vram = item.get("sizeVram")
            ram_pct, vram_pct = (
                _split(size - vram, vram)
                if isinstance(size, int) and isinstance(vram, int) and 0 <= vram <= size
                else (None, None)
            )
            models.append(
                {
                    "id": item["name"],
                    "name": item["name"],
                    "runtime": "ollama",
                    "roles": self._ollama_roles(item["name"]),
                    "ramPct": ram_pct,
                    "vramPct": vram_pct,
                    "approximate": False,
                    "loading": False,
                }
            )
        return sorted(models, key=lambda model: model["name"])

    # vLLM keeps everything on the GPU here (no CPU offload in Compose).
    def _vllm(self, status: dict[str, Any]) -> list[LocalModel]:
        services: dict[str, Any] = {
            **(status.get("managed") or {}),
            **(status.get("observed") or {}),
        }
        reports = {
            spec.vllm_service: model
            for model, spec in REPORT_MODELS.items()
            if spec.provider == "vllm" and spec.vllm_service
        }
        models: list[LocalModel] = []
        for service in sorted(services):
            item = services[service]
            state = item.get("state") if isinstance(item, dict) else None
            if state not in _RUNNING_STATES:
                continue
            name: str
            role: LocalModelRole
            if service in reports:
                name, role = reports[service], "report"
            elif service in _VLLM_OTHERS:
                name, role = _VLLM_OTHERS[service]
            else:
                continue
            models.append(
                {
                    "id": service,
                    "name": name,
                    "runtime": "vllm",
                    "roles": [role],
                    "ramPct": 0,
                    "vramPct": 100,
                    "approximate": False,
                    "loading": state != "running" or not self._healthy(service),
                }
            )
        return models

    def _healthy(self, service: str) -> bool:
        try:
            response = self._http.get(
                _VLLM_HEALTH_URL.format(service=service), timeout=_HEALTH_TIMEOUT
            )
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    # The agent's figures are an estimate: the VRAM it gave Colibri and the engine's working set.
    def _colibri(self, item: Any) -> list[LocalModel]:
        if not isinstance(item, dict):
            return []
        name = next(
            (model for model, spec in REPORT_MODELS.items() if spec.provider == "colibri"), None
        )
        if name is None:
            return []
        ram, vram = item.get("ramGb"), item.get("vramGb")
        ram_pct, vram_pct = (
            _split(float(ram), float(vram))
            if isinstance(ram, (int, float)) and isinstance(vram, (int, float))
            else (None, None)
        )
        return [
            {
                "id": "colibri",
                "name": name,
                "runtime": "colibri",
                "roles": ["report"],
                "ramPct": ram_pct,
                "vramPct": vram_pct,
                "approximate": True,
                "loading": bool(item.get("loading")),
            }
        ]
