"""Minimal medical context collected before report generation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

HEALTH_PROBLEM_QUESTION = "Pentru ce problema de sanatate doriti recomandari naturiste?"


@dataclass
class HealthProfile:
    health_problem: str = ""
    health_context: list[str] = field(default_factory=list)
    transcript: list[dict[str, str]] = field(default_factory=list)
    asked_field: str | None = None

    def add_transcript(self, role: str, content: str) -> None:
        clean = " ".join((content or "").split())[:4000]
        if role in {"assistant", "user"} and clean:
            self.transcript.append({"role": role, "content": clean})

    def add_health_context(self, message: str) -> None:
        clean = " ".join((message or "").split())[:4000]
        if clean and clean.casefold() not in {value.casefold() for value in self.health_context}:
            self.health_context.append(clean)

    def set_health_problem(self, message: str) -> None:
        clean = " ".join((message or "").split())[:4000]
        if clean:
            self.health_problem = clean
            self.add_health_context(clean)
            self.asked_field = None

    @property
    def report_ready(self) -> bool:
        return bool(self.health_problem)

    def next_question(self) -> str | None:
        if not self.health_problem:
            self.asked_field = "health_problem"
            return HEALTH_PROBLEM_QUESTION
        self.asked_field = None
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "health_problem": self.health_problem,
            "health_context": list(self.health_context),
            "transcript": [dict(entry) for entry in self.transcript],
        }
