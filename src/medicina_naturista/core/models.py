"""Minimal medical context collected before report generation."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HEALTH_PROBLEM_QUESTION = "Bine ați venit în cabinetul meu. Eu nu am acces la leacuri de pe internet, nici nu întreb AI-ul dar am multe cărți scanate și mă voi uita rapid în ele pentru a găsi recomandări de tratamente naturiste adjuvante pentru afecțiunea d-voastră. Vă rog să-mi spuneți care este problema de sănătate cu care vă confruntați."

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


@dataclass
class SessionData:
    """Ephemeral state isolated to one browser tab."""

    cookie_id: str
    tab_id: str
    directory: Path
    created_at: float = field(default_factory=time.monotonic)
    last_seen: float = field(default_factory=time.monotonic)
    profile: HealthProfile = field(default_factory=HealthProfile)
    history: list[dict[str, str]] = field(default_factory=list)
    report_bytes: bytes | None = None
    report_id: str | None = None
    # Evidence found by the retrieval-only stage, shown to the patient before
    # they choose to send it to the AI. Consumed (not recomputed) by report
    # generation, so the fragments the patient reviewed are exactly the ones sent.
    pending_evidence: dict[str, dict[str, str]] | None = None
    # Set when the last chat message was an email address for the finished
    # report, so the chained retrieval step does not treat it as a health problem.
    email_request_handled: bool = False
    lock: threading.RLock = field(default_factory=threading.RLock)

    def touch(self) -> None:
        """Refresh the session's last-activity timestamp."""
        self.last_seen = time.monotonic()

    def clear_report(self) -> None:
        """Discard the generated report and download identifier."""
        self.report_bytes = None
        self.report_id = None
