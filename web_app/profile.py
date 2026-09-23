"""Structured, correction-friendly information collected from the consultation."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

NUMERIC_FIELDS = ("age", "weight_kg", "height_cm")
QUESTIONS = {
    "full_name": "Cum vă numiți? Vă rog să introduceți numele și prenumele.",
    "age": "Ce vârstă aveți? Puteți răspunde și «nu știu» sau «prefer să nu spun».",
    "weight_kg": "Care este greutatea aproximativă în kilograme?",
    "height_cm": "Care este înălțimea aproximativă în centimetri?",
    "health_problem": (
        "Pentru ce problemă de sănătate doriți recomandări naturiste? Puteți descrie liber "
        "denumirea problemei, simptomele, evoluția și orice alte detalii considerați relevante."
    ),
}
UNKNOWN_RE = re.compile(
    r"^\s*(nu [șs]tiu|nu cunosc|nu sunt sigur[ăa]?|nu am (aceast[ăa] )?informa[țt]ie|"
    r"prefer s[ăa] nu (spun|r[ăa]spund)|necunoscut[ăa]?)[.! ]*$",
    re.I,
)


def _items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            clean = " ".join(item.split())[:160]
            if clean and clean.casefold() not in {x.casefold() for x in result}:
                result.append(clean)
    return result[:20]


@dataclass
class HealthProfile:
    full_name: str = ""
    health_conditions: list[str] = field(default_factory=list)
    symptoms: list[str] = field(default_factory=list)
    age: int | None = None
    sex: str | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    medications: list[str] = field(default_factory=list)
    allergies: list[str] = field(default_factory=list)
    health_problem: str = ""
    health_context: list[str] = field(default_factory=list)
    transcript: list[dict[str, str]] = field(default_factory=list)
    follow_up_questions: list[str] = field(default_factory=list)
    follow_up_answers: list[str] = field(default_factory=list)
    follow_up_index: int = 0
    follow_up_status: str = "not_started"
    unknown: set[str] = field(default_factory=set)
    completed_fields: set[str] = field(default_factory=set)
    asked_field: str | None = None

    def set_full_name(self, message: str) -> None:
        clean = " ".join(message.split())[:120]
        if len(clean.split()) >= 2:
            self.full_name = clean
            self.asked_field = None

    def add_transcript(self, role: str, content: str) -> None:
        clean = " ".join((content or "").split())[:4000]
        if role in {"assistant", "user"} and clean:
            self.transcript.append({"role": role, "content": clean})

    def add_health_context(self, message: str) -> None:
        clean = " ".join((message or "").split())[:4000]
        if clean and clean.casefold() not in {value.casefold() for value in self.health_context}:
            self.health_context.append(clean)

    def mark_unknown_answer(self, message: str) -> bool:
        if self.asked_field in NUMERIC_FIELDS and UNKNOWN_RE.match(message):
            setattr(self, self.asked_field, None)
            self.unknown.add(self.asked_field)
            self.completed_fields.add(self.asked_field)
            self.asked_field = None
            return True
        return False

    def merge(self, update: dict[str, Any], scalar_field: str | None = None) -> None:
        for name in ("health_conditions", "symptoms", "medications", "allergies"):
            for item in _items(update.get(name)):
                target = getattr(self, name)
                if item.casefold() not in {x.casefold() for x in target}:
                    target.append(item)
        values = {
            "age": (int, 0, 120),
            "weight_kg": (float, 2, 500),
            "height_cm": (float, 40, 260),
        }
        selected = (scalar_field,) if scalar_field in values else tuple(values)
        for name in selected:
            converter, low, high = values[name]
            raw = update.get(name)
            if raw is None or raw == "":
                continue
            try:
                number = converter(str(raw).replace(",", "."))
            except (ValueError, TypeError):
                continue
            if low <= number <= high:
                setattr(self, name, number)
                self.unknown.discard(name)
                if scalar_field == name:
                    self.completed_fields.add(name)
        sex = update.get("sex")
        if isinstance(sex, str) and sex.strip():
            self.sex = sex.strip()[:60]
        for name in update.get("unknown_fields", []):
            if name in NUMERIC_FIELDS and (scalar_field is None or name == scalar_field) and getattr(self, name) is None:
                self.unknown.add(name)
                if scalar_field == name:
                    self.completed_fields.add(name)
        if self.asked_field in NUMERIC_FIELDS and (
            getattr(self, self.asked_field) is not None or self.asked_field in self.unknown
        ):
            self.asked_field = None

    def set_health_problem(self, message: str) -> None:
        clean = " ".join(message.split())[:4000]
        if clean:
            self.health_problem = clean
            self.add_health_context(clean)
            self.asked_field = None

    def set_follow_up_questions(self, questions: list[str]) -> None:
        if self.follow_up_status != "not_started":
            return
        self.follow_up_questions = questions[:10]
        self.follow_up_answers = []
        self.follow_up_index = 0
        self.follow_up_status = "ready" if self.follow_up_questions else "failed"
        self.asked_field = "follow_up" if self.follow_up_questions else None

    def fail_follow_up(self) -> None:
        if self.follow_up_status == "not_started":
            self.follow_up_status = "failed"
            self.asked_field = None

    @property
    def current_follow_up_question(self) -> str | None:
        if self.follow_up_status != "ready" or self.follow_up_index >= len(self.follow_up_questions):
            return None
        return self.follow_up_questions[self.follow_up_index]

    @property
    def remaining_follow_up_count(self) -> int:
        if self.follow_up_status != "ready":
            return 0
        return max(0, len(self.follow_up_questions) - self.follow_up_index)

    @property
    def report_ready(self) -> bool:
        return bool(self.health_problem) and self.follow_up_status in {"completed", "failed"}

    def record_follow_up_answer(self, message: str) -> None:
        if self.follow_up_status != "ready" or self.current_follow_up_question is None:
            return
        clean = " ".join(message.split())[:4000]
        self.follow_up_answers.append(clean)
        self.add_health_context(clean)
        self.follow_up_index += 1
        if self.follow_up_index >= len(self.follow_up_questions):
            self.follow_up_status = "completed"
            self.asked_field = None
        else:
            self.asked_field = "follow_up"

    def next_question(self) -> str | None:
        if not self.full_name:
            self.asked_field = "full_name"
            return QUESTIONS["full_name"]
        for name in NUMERIC_FIELDS:
            if name not in self.completed_fields:
                self.asked_field = name
                return QUESTIONS[name]
        if not self.health_problem:
            self.asked_field = "health_problem"
            return QUESTIONS["health_problem"]
        if self.follow_up_status == "ready":
            self.asked_field = "follow_up"
            return self.current_follow_up_question
        self.asked_field = None
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "full_name": self.full_name,
            "health_conditions": self.health_conditions,
            "symptoms": self.symptoms,
            "age": self.age,
            "sex": self.sex,
            "weight_kg": self.weight_kg,
            "height_cm": self.height_cm,
            "medications": self.medications,
            "allergies": self.allergies,
            "health_problem": self.health_problem,
            "health_context": list(self.health_context),
            "transcript": [dict(entry) for entry in self.transcript],
            "follow_up_status": self.follow_up_status,
            "unknown_fields": sorted(self.unknown),
        }
