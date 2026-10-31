"""Map the user-selected report effort to each provider's own reasoning parameter."""

from __future__ import annotations

from typing import Final

from backend.core.report_models import ReportEffort

# Responses API `reasoning.effort`. `low` switches reasoning off ("none"): xAI documents
# none/low/medium/high for grok-4.3 and DeepSeek documents none/low/high/max, mapping
# `medium` to `high` itself. Hugging Face lists only low/medium/high, so its "none" is
# unconfirmed for the DeepInfra route and must be checked against a live request.
RESPONSES_EFFORT: Final[dict[ReportEffort, str]] = {
    "low": "none",
    "medium": "medium",
    "high": "high",
}


# Ollama's `think` is a boolean for these models, so medium and high are the same request.
def ollama_think(effort: ReportEffort) -> bool:
    return effort != "low"


def responses_effort(effort: ReportEffort) -> str:
    return RESPONSES_EFFORT[effort]
