"""The admin's control of the multilevel learning (plan 2026-11-27, 5.4b): state, start and stop.

The build never runs in the web process: the LLM host agent runs scripts.build_knowledge on the
host, reached through the report runtime's orchestrator relay. The state joins the agent's jobs
with the runs in the database, so it survives app restarts and shows the same in every tab.
"""

from __future__ import annotations

from collections.abc import Callable

from backend.ai.index_state import IndexUnavailable
from backend.ai.knowledge_l1 import prompt_sha256
from backend.ai.model_runtime import VllmRuntime
from backend.config import Settings
from backend.core.errors import ApplicationError
from backend.core.language import LANGUAGES
from backend.core.learning import (
    LEVELS,
    LearningSnapshot,
    LearningState,
    learning_state,
    plan_start,
    published_levels,
)
from backend.core.texts import tr


def knowledge_models(settings: Settings) -> dict[int, str]:
    return {
        1: settings.knowledge_l1_model,
        2: settings.knowledge_l2_model,
        3: settings.knowledge_l3_model,
        4: settings.knowledge_l4_model,
    }


class LearningControl:
    def __init__(
        self,
        settings: Settings,
        snapshot: Callable[[], LearningSnapshot],
        runtime: VllmRuntime | None,
    ) -> None:
        self._models = knowledge_models(settings)
        self._snapshot = snapshot
        self._runtime = runtime

    def _prompts(self) -> dict[tuple[int, str], str]:
        return {(1, language): prompt_sha256(language) for language in LANGUAGES}

    def _require_runtime(self) -> VllmRuntime:
        if self._runtime is None:
            raise ApplicationError(
                "LLM_ORCHESTRATOR_UNAVAILABLE", tr("errors.llm_orchestrator_unavailable"), 503
            )
        return self._runtime

    def state(self) -> LearningState:
        jobs = self._runtime.knowledge_jobs() if self._runtime is not None else None
        return learning_state(self._snapshot(), jobs, self._models, self._prompts())

    # Refused during an index sync (the build would be refused too) and beside a build this app
    # did not start; a level whose lower level is not published needs include_lower.
    def start(self, level: int | None, include_lower: bool) -> LearningState:
        runtime = self._require_runtime()
        snapshot = self._snapshot()
        jobs = runtime.knowledge_jobs()
        if jobs is None:
            raise ApplicationError(
                "LLM_HOST_AGENT_UNAVAILABLE", tr("errors.llm_host_agent_unavailable"), 503
            )
        if snapshot.index_maintenance:
            raise IndexUnavailable()
        if snapshot.build_lock_held and not jobs.active:
            raise ApplicationError(
                "KNOWLEDGE_BUILD_RUNNING", tr("errors.knowledge_build_running"), 409
            )
        levels = plan_start(level, include_lower, published_levels(snapshot), jobs.scheduled)
        runtime.start_knowledge(levels)
        return self.state()

    # None stops every level, a build started by hand included.
    def stop(self, level: int | None) -> LearningState:
        self._require_runtime().stop_knowledge(LEVELS if level is None else (level,))
        return self.state()
