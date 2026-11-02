"""Shared progress helpers and the public safety command, which uses product knowledge."""

from __future__ import annotations

import math
from typing import Any

from backend.config import Settings


# Durations keep total hours rather than wrapping at a day boundary.
def format_duration(seconds: float) -> str:
    hours, remainder = divmod(max(0, int(seconds)), 3600)
    minutes, seconds_part = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds_part:02d}"


# Attempts and cache hits do not supply a measured processing rate for pending batches.
def batch_progress(completed: int, total: int | None, elapsed: float) -> dict[str, Any]:
    rate = completed / elapsed if elapsed > 0 else 0.0
    eta = None
    if total is not None:
        remaining = max(0, total - completed)
        if remaining == 0:
            eta = "00:00:00"
        elif rate > 0:
            eta = format_duration(max(1, math.ceil(remaining / rate)))
    return {"rate_batches_second": rate, "ETA(hh:mm:ss)": eta}


# Completed AI batches do not estimate inventory, projections, or publication still pending.
def workflow_progress(
    counters: dict[str, Any], elapsed: float, warning_metrics: dict[str, Any] | None = None
) -> dict[str, Any]:
    stage = counters.get("progress_stage", "analysis")
    metrics = batch_progress(0, None, elapsed)
    if stage == "associations":
        metrics = batch_progress(counters["completed"], counters.get("batches"), elapsed)
    elif stage in {"warnings_only", "product_safety"} and warning_metrics is not None:
        metrics = dict(warning_metrics)
    if counters.get("status") in {"ready", "published"}:
        metrics = dict(warning_metrics or metrics)
        metrics["ETA(hh:mm:ss)"] = "00:00:00"
    elif counters.get("status") == "failed" or metrics["ETA(hh:mm:ss)"] == "00:00:00":
        metrics["ETA(hh:mm:ss)"] = None
    return {**metrics, "progress_stage": stage}


def run_safety_index(
    settings: Settings,
    *,
    analyze: bool = False,
    publish: str | None = None,
    resume: str | None = None,
) -> dict[str, Any]:
    from scripts.herb_product_safety_index import run_product_safety_index

    return run_product_safety_index(settings, analyze=analyze, publish=publish, resume=resume)
