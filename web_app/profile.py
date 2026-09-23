"""Structured, correction-friendly information collected from free conversation."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

FIELDS = ("age", "sex", "weight_kg", "height_cm")
QUESTIONS = {
    "age": "Ce vârstă aveți? Puteți răspunde și «nu știu» sau «prefer să nu spun».",
    "sex": "Ce sex doriți să menționați pentru contextul recomandărilor?",
    "weight_kg": "Care este greutatea aproximativă în kilograme?",
    "height_cm": "Care este înălțimea aproximativă în centimetri?",
}
UNKNOWN_RE = re.compile(r"^\s*(nu [șs]tiu|nu cunosc|nu sunt sigur[ăa]?|nu am (aceast[ăa] )?informa[țt]ie|prefer s[ăa] nu (spun|r[ăa]spund)|necunoscut[ăa]?)[.! ]*$", re.I)


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
    health_conditions: list[str] = field(default_factory=list)
    symptoms: list[str] = field(default_factory=list)
    age: int | None = None
    sex: str | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    medications: list[str] = field(default_factory=list)
    allergies: list[str] = field(default_factory=list)
    unknown: set[str] = field(default_factory=set)
    asked_field: str | None = None

    def mark_unknown_answer(self, message: str) -> bool:
        if self.asked_field in FIELDS and UNKNOWN_RE.match(message):
            setattr(self, self.asked_field, None)
            self.unknown.add(self.asked_field)
            self.asked_field = None
            return True
        return False

    def merge(self, update: dict[str, Any]) -> None:
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
        for name, (converter, low, high) in values.items():
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
        sex = update.get("sex")
        if isinstance(sex, str) and sex.strip():
            self.sex = sex.strip()[:60]
            self.unknown.discard("sex")
        for name in update.get("unknown_fields", []):
            if name in FIELDS and getattr(self, name) is None:
                self.unknown.add(name)
        if self.asked_field and (getattr(self, self.asked_field) is not None or self.asked_field in self.unknown):
            self.asked_field = None

    def next_question(self) -> str | None:
        if not (self.health_conditions or self.symptoms):
            return "Descrieți, vă rog, problemele sau simptomele pentru care doriți informații."
        for name in FIELDS:
            if getattr(self, name) is None and name not in self.unknown:
                self.asked_field = name
                return QUESTIONS[name]
        self.asked_field = None
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "health_conditions": self.health_conditions,
            "symptoms": self.symptoms,
            "age": self.age,
            "sex": self.sex,
            "weight_kg": self.weight_kg,
            "height_cm": self.height_cm,
            "medications": self.medications,
            "allergies": self.allergies,
            "unknown_fields": sorted(self.unknown),
        }
