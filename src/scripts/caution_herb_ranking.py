"""Prepare and publish warning projections using indexed data and caches only, without AI."""

from __future__ import annotations

import json
import time

from backend.ai.herb_caution_repository import CautionRepository
from backend.config import Settings
from backend.core.operation_context import OperationBudget, operation_budget


def run_caution_ranking(settings: Settings, *, publish: str | None = None) -> dict:
    repository = CautionRepository()
    with operation_budget(
        OperationBudget(
            time.monotonic() + settings.herb_association_build_timeout_seconds,
            time.monotonic,
            lambda: None,
        )
    ):
        if publish is not None:
            repository.publish(publish, settings)
            result = {"run_id": publish, "status": "published", "ai_requests_sent_total": 0}
        else:
            result = repository.prepare(repository.active_positive(settings), settings)
    print(json.dumps({"stage": "caution_ranking", **result}), flush=True)
    return result
