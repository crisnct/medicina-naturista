"""Pure rules of the multilevel learning control (plan 2026-11-27, 5.4b): level states, the order the
levels start in and the time left.

No I/O: the database snapshot and the LLM host agent's jobs come in as values. A level builds on a
published lower level, one level runs at a time, and the time left is the units left times a moving
average of the seconds per unit that the build keeps itself, so pauses never enter it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, TypedDict

from backend.core.errors import ApplicationError
from backend.core.language import LANGUAGES
from backend.core.texts import tr

LEVELS = (1, 2, 3, 4)
# The levels scripts/build_knowledge.py can build so far; the others are shown, but not started.
IMPLEMENTED_LEVELS = (1,)
# Statuses of an unfinished full run, which the next start of its level continues.
UNFINISHED_STATUSES = frozenset({"queued", "running", "paused", "stopping", "failed"})
# Weight of the newest sample in the moving average of the seconds per unit: the estimate follows a
# change of speed within a few samples and does not jump on one slow batch.
SPEED_SMOOTHING = 0.3
# Units per speed sample (about a minute of level 1 on vLLM); before the first one the time left is
# unknown, unless an earlier run with the same model gave a speed to start from.
SPEED_SAMPLE_UNITS = 20

LevelStatus = Literal[
    "not_implemented",
    "running",
    "stopping",
    "paused_for_report",
    "queued",
    "published",
    "partial",
    "stopped",
    "failed",
    "not_built",
]
# Why a published level needs a new run: another model or prompt, a changed index (level 1), or a
# lower level published after it.
OutdatedReason = Literal["model", "prompt", "index", "lower_level"]


@dataclass(frozen=True)
class KnowledgeRun:
    run_id: int
    language: str
    level: int
    model: str
    prompt_sha256: str
    status: str
    is_active: bool
    units_total: int | None
    units_done: int
    published_utc: datetime | None
    counters: Mapping[str, Any]

    @property
    def unfinished(self) -> bool:
        return not self.is_active and self.status in UNFINISHED_STATUSES

    @property
    def seconds_per_unit(self) -> float | None:
        value = self.counters.get("seconds_per_unit")
        return float(value) if isinstance(value, (int, float)) and value > 0 else None


@dataclass(frozen=True)
class LearningSnapshot:
    # The newest full run (samples excluded) and the published run of each language and level.
    latest: tuple[KnowledgeRun, ...]
    active: tuple[KnowledgeRun, ...]
    # Distinct fragment texts per language: the units of a new level-1 run.
    fragments: Mapping[str, int]
    index_generation: str | None
    # An index sync holds the index lock: a build would be refused.
    index_maintenance: bool
    # Some process holds the knowledge build lock (the agent's build, or one started by hand).
    build_lock_held: bool
    # Seconds per unit of the newest finished run of each level with its configured model.
    previous_speed: Mapping[int, float]


@dataclass(frozen=True)
class BuildJobs:
    """The LLM host agent's knowledge jobs: the level whose process runs (`active`) or waits for a
    local report to end (`paused`), and the levels queued after it."""

    level: int | None
    active: bool
    stopping: bool
    paused: bool
    queue: tuple[int, ...]
    last: Mapping[str, Any] | None

    # The agent's reply is checked field by field; anything malformed counts as no job.
    @classmethod
    def from_agent(cls, reply: Mapping[str, Any]) -> BuildJobs:
        level = reply.get("level")
        queue = reply.get("queue")
        last = reply.get("last")
        return cls(
            level if isinstance(level, int) and level in LEVELS else None,
            reply.get("active") is True,
            reply.get("stopping") is True,
            reply.get("paused") is True,
            tuple(item for item in queue if isinstance(item, int) and item in LEVELS)
            if isinstance(queue, list)
            else (),
            last if isinstance(last, dict) else None,
        )

    @property
    def scheduled(self) -> frozenset[int]:
        return frozenset({*self.queue, *((self.level,) if self.level is not None else ())})


class LanguageState(TypedDict):
    language: str
    runStatus: str | None
    published: str | None
    model: str | None
    unitsDone: int | None
    unitsTotal: int | None
    outdated: list[OutdatedReason]


class LevelState(TypedDict):
    level: int
    implemented: bool
    model: str
    status: LevelStatus
    phase: str | None
    unitsDone: int | None
    unitsTotal: int | None
    etaSeconds: int | None
    outdated: list[OutdatedReason]
    languages: list[LanguageState]


class LearningState(TypedDict):
    agentAvailable: bool
    indexMaintenance: bool
    externalBuild: bool
    pausedForReport: bool
    queue: list[int]
    lastExit: dict[str, Any] | None
    levels: list[LevelState]


def update_speed(previous: float | None, sample: float) -> float:
    if previous is None or previous <= 0:
        return sample
    return SPEED_SMOOTHING * sample + (1 - SPEED_SMOOTHING) * previous


# A published run that a new run would only repeat: same model and prompt, built from this index.
def up_to_date(
    run: KnowledgeRun, model: str, prompt_sha256: str | None, index_generation: str | None
) -> bool:
    return (
        run.model == model
        and run.prompt_sha256 == prompt_sha256
        and run.counters.get("index_generation") == index_generation
    )


def published_levels(snapshot: LearningSnapshot) -> frozenset[int]:
    keys = {(run.level, run.language) for run in snapshot.active}
    return frozenset(
        level for level in LEVELS if all((level, language) in keys for language in LANGUAGES)
    )


# The levels a start runs, lowest first. A level whose lower level is neither published nor already
# running or queued needs the admin's consent to build that one first (include_lower).
def plan_start(
    level: int | None,
    include_lower: bool,
    published: frozenset[int],
    scheduled: frozenset[int],
) -> tuple[int, ...]:
    if level is None:
        return IMPLEMENTED_LEVELS
    if level not in IMPLEMENTED_LEVELS:
        raise ApplicationError(
            "KNOWLEDGE_LEVEL_NOT_IMPLEMENTED",
            tr("errors.knowledge_level_not_implemented", level=level),
            409,
        )
    plan = [level]
    lower = level - 1
    while lower >= 1 and lower not in published and lower not in scheduled:
        if not include_lower:
            raise ApplicationError(
                "KNOWLEDGE_LOWER_LEVEL_REQUIRED",
                tr("errors.knowledge_lower_level_required", level=level, lower=lower),
                409,
            )
        if lower not in IMPLEMENTED_LEVELS:
            raise ApplicationError(
                "KNOWLEDGE_LEVEL_NOT_IMPLEMENTED",
                tr("errors.knowledge_level_not_implemented", level=lower),
                409,
            )
        plan.insert(0, lower)
        lower -= 1
    return tuple(plan)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _outdated(
    run: KnowledgeRun,
    model: str,
    prompt: str | None,
    index_generation: str | None,
    lower: KnowledgeRun | None,
) -> list[OutdatedReason]:
    reasons: list[OutdatedReason] = []
    if run.model != model:
        reasons.append("model")
    if prompt is not None and run.prompt_sha256 != prompt:
        reasons.append("prompt")
    if run.level == 1 and run.counters.get("index_generation") != index_generation:
        reasons.append("index")
    if (
        lower is not None
        and lower.published_utc is not None
        and run.published_utc is not None
        and run.published_utc < lower.published_utc
    ):
        reasons.append("lower_level")
    return reasons


def _status(
    level: int,
    jobs: BuildJobs | None,
    latest: Sequence[KnowledgeRun | None],
    active: Sequence[KnowledgeRun | None],
) -> LevelStatus:
    if level not in IMPLEMENTED_LEVELS:
        return "not_implemented"
    if jobs is not None and jobs.level == level and jobs.active:
        return "stopping" if jobs.stopping else "running"
    if jobs is not None and jobs.level == level and jobs.paused:
        return "paused_for_report"
    if jobs is not None and level in jobs.queue:
        return "queued"
    unfinished = [run for run in latest if run is not None and run.unfinished]
    if unfinished:
        return "failed" if any(run.status == "failed" for run in unfinished) else "stopped"
    published = sum(run is not None for run in active)
    if published == len(active):
        return "published"
    return "partial" if published else "not_built"


# Units done and in all of level 1 for the languages a start would process: an unfinished run
# continues, a published run that is up to date is skipped, any other language starts over with
# every distinct fragment. The higher levels count their units when they are built.
def _level_one_work(
    latest: Mapping[str, KnowledgeRun],
    active: Mapping[str, KnowledgeRun],
    snapshot: LearningSnapshot,
    model: str,
    prompts: Mapping[str, str],
) -> tuple[int, int]:
    done = total = 0
    for language in LANGUAGES:
        run = latest.get(language)
        published = active.get(language)
        if run is not None and run.unfinished:
            done += run.units_done
            total += run.units_total or snapshot.fragments.get(language, 0)
        elif published is not None and up_to_date(
            published, model, prompts.get(language), snapshot.index_generation
        ):
            continue
        else:
            total += snapshot.fragments.get(language, 0)
    return done, total


def _speed(level: int, runs: Sequence[KnowledgeRun], snapshot: LearningSnapshot) -> float | None:
    unfinished = [run for run in runs if run.unfinished and run.seconds_per_unit is not None]
    unfinished.sort(key=lambda run: run.status not in ("running", "stopping"))
    if unfinished:
        return unfinished[0].seconds_per_unit
    return snapshot.previous_speed.get(level)


def learning_state(
    snapshot: LearningSnapshot,
    jobs: BuildJobs | None,
    models: Mapping[int, str],
    prompts: Mapping[tuple[int, str], str],
) -> LearningState:
    latest = {(run.level, run.language): run for run in snapshot.latest}
    active = {(run.level, run.language): run for run in snapshot.active}
    levels: list[LevelState] = []
    for level in LEVELS:
        model = models[level]
        level_latest = [latest.get((level, language)) for language in LANGUAGES]
        level_active = [active.get((level, language)) for language in LANGUAGES]
        status = _status(level, jobs, level_latest, level_active)
        languages: list[LanguageState] = []
        reasons: list[OutdatedReason] = []
        for language, run, published in zip(LANGUAGES, level_latest, level_active, strict=True):
            outdated = (
                _outdated(
                    published,
                    model,
                    prompts.get((level, language)),
                    snapshot.index_generation,
                    active.get((level - 1, language)),
                )
                if published is not None
                else []
            )
            reasons.extend(reason for reason in outdated if reason not in reasons)
            languages.append(
                {
                    "language": language,
                    "runStatus": run.status if run is not None else None,
                    "published": _iso(published.published_utc) if published is not None else None,
                    "model": published.model if published is not None else None,
                    "unitsDone": run.units_done if run is not None else None,
                    "unitsTotal": run.units_total if run is not None else None,
                    "outdated": outdated,
                }
            )
        units_done = units_total = eta = None
        phase = None
        if level == 1 and status in ("running", "stopping", "paused_for_report"):
            units_done, units_total = _level_one_work(
                {language: run for language, run in zip(LANGUAGES, level_latest) if run},
                {language: run for language, run in zip(LANGUAGES, level_active) if run},
                snapshot,
                model,
                {
                    language: prompts[(1, language)]
                    for language in LANGUAGES
                    if (1, language) in prompts
                },
            )
            running = [run for run in level_latest if run is not None and run.unfinished]
            speed = _speed(level, running, snapshot)
            if speed is not None and status != "stopping":
                eta = round(max(0, units_total - units_done) * speed)
            phase = next(
                (
                    str(run.counters["phase"])
                    for run in running
                    if run.status in ("running", "stopping") and "phase" in run.counters
                ),
                None,
            )
        levels.append(
            {
                "level": level,
                "implemented": level in IMPLEMENTED_LEVELS,
                "model": model,
                "status": status,
                "phase": phase,
                "unitsDone": units_done,
                "unitsTotal": units_total,
                "etaSeconds": eta,
                "outdated": reasons,
                "languages": languages,
            }
        )
    return {
        "agentAvailable": jobs is not None,
        "indexMaintenance": snapshot.index_maintenance,
        "externalBuild": snapshot.build_lock_held and not (jobs is not None and jobs.active),
        "pausedForReport": jobs is not None and jobs.paused,
        "queue": list(jobs.queue) if jobs is not None else [],
        "lastExit": dict(jobs.last) if jobs is not None and jobs.last is not None else None,
        "levels": levels,
    }
