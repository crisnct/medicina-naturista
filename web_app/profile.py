"""Minimal medical context collected before report generation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

HEALTH_PROBLEM_QUESTION = "Bine ați venit în cabinetul meu. Eu nu am acces la leacuri de pe internet, nici nu întreb chatGPT dar am multe cărți scanate și mă voi uita rapid în ele pentru a găsi recomandări de tratamente naturiste adjuvante pentru afecțiunea d-voastră. Vă rog să-mi spuneți care este problema de sănătate cu care vă confruntați."

@dataclass
class HealthProfile:
    health_problem: str = ""
    health_context: list[str] = field(default_factory=list)
    transcript: list[dict[str, str]] = field(default_factory=list)
    asked_field: str | None = None

    # Store a normalized conversation entry when its role and content are allowed.
    def add_transcript(self, role: str, content: str) -> None:
        clean = " ".join((content or "").split())[:4000]
        if role in {"assistant", "user"} and clean:
            self.transcript.append({"role": role, "content": clean})

    # Add a unique normalized user detail to the profile context.
    def add_health_context(self, message: str) -> None:
        clean = " ".join((message or "").split())[:4000]
        if clean and clean.casefold() not in {value.casefold() for value in self.health_context}:
            self.health_context.append(clean)

    # Set the primary health problem and add it to the searchable context.
    def set_health_problem(self, message: str) -> None:
        clean = " ".join((message or "").split())[:4000]
        if clean:
            self.health_problem = clean
            self.add_health_context(clean)
            self.asked_field = None

    # Start a distinct report context and discard medical details from the
    # previously generated report while leaving the visual chat history intact.
    def replace_health_problem(self, message: str) -> None:
        clean = " ".join((message or "").split())[:4000]
        if not clean:
            return
        self.health_problem = clean
        self.health_context = [clean]
        self.transcript = [{"role": "user", "content": clean}]
        self.asked_field = None

    @property
    # Indicate whether the profile contains enough information to generate a report.
    def report_ready(self) -> bool:
        return bool(self.health_problem)

    # Return the next required profile question, if the health problem is missing.
    def next_question(self) -> str | None:
        if not self.health_problem:
            self.asked_field = "health_problem"
            return HEALTH_PROBLEM_QUESTION
        self.asked_field = None
        return None

    # Serialize the profile into the structure consumed by retrieval and AI generation.
    def as_dict(self) -> dict[str, Any]:
        return {
            "health_problem": self.health_problem,
            "health_context": list(self.health_context),
            "transcript": [dict(entry) for entry in self.transcript],
        }
