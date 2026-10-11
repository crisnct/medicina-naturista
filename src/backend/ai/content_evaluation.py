"""Content-labelled retrieval metrics. No network, database or personal corpus I/O."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FragmentKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    path: str
    text_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def relative_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            not value
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in value
            or ":" in value
            or value != str(path)
        ):
            raise ValueError("fragment path must be a normalized relative POSIX path")
        return value

    @property
    def identity(self) -> str:
        return f"{self.path}:{self.text_hash}"

    @classmethod
    def from_text(cls, path: str, text: str) -> FragmentKey:
        return cls(path=path, text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest())


class Judgement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fragment: FragmentKey
    grade: int = Field(ge=0, le=3, strict=True)
    warning_ids: list[str] = Field(default_factory=list)


class ContentCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    category: str = Field(min_length=1)
    kind: Literal["condition", "synonym", "free_text", "warning"]
    judgements: list[Judgement] = Field(min_length=1)
    expected_warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def complete(self) -> ContentCase:
        if not self.query.strip() or not self.id.strip() or not self.category.strip():
            raise ValueError("case fields must not be blank")
        keys = [item.fragment.identity for item in self.judgements]
        if len(keys) != len(set(keys)) or not any(item.grade > 0 for item in self.judgements):
            raise ValueError("judgements must be unique and include a relevant fragment")
        expected = set(self.expected_warnings)
        available = {
            warning for item in self.judgements if item.grade > 0 for warning in item.warning_ids
        }
        if len(expected) != len(self.expected_warnings) or not expected <= available:
            raise ValueError("expected warnings must be unique and backed by relevant judgements")
        if self.kind == "warning" and not expected:
            raise ValueError("warning cases must label an expected warning")
        return self


class ContentSuite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    description: str
    annotation_method: str
    cases: list[ContentCase] = Field(min_length=30, max_length=30)

    @model_validator(mode="after")
    def coverage(self) -> ContentSuite:
        if len({case.id for case in self.cases}) != 30:
            raise ValueError("exactly 30 unique cases are required")
        if {case.kind for case in self.cases} != {"condition", "synonym", "free_text", "warning"}:
            raise ValueError("all four query kinds must be covered")
        return self


def load_suite(path: Path) -> ContentSuite:
    return ContentSuite.model_validate_json(path.read_text(encoding="utf-8"))


def fingerprint(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_fragments(suite: ContentSuite, corpus: Sequence[FragmentKey]) -> None:
    available = {key.identity for key in corpus}
    missing = {
        item.fragment.identity for case in suite.cases for item in case.judgements
    } - available
    if missing:
        raise ValueError(f"{len(missing)} labelled fragments no longer resolve in this corpus")


def metrics(case: ContentCase, ranked: Sequence[FragmentKey]) -> dict[str, Any]:
    keys = [key.identity for key in ranked]
    if len(keys) != len(set(keys)):
        raise ValueError("ranked fragments must be unique")
    labels = {item.fragment.identity: item for item in case.judgements}
    relevant = {key for key, item in labels.items() if item.grade > 0}
    grades = [labels[key].grade if key in labels else 0 for key in keys[:10]]
    dcg = sum((2**grade - 1) / math.log2(position + 2) for position, grade in enumerate(grades))
    ideal = sorted((item.grade for item in labels.values()), reverse=True)[:10]
    idcg = sum((2**grade - 1) / math.log2(position + 2) for position, grade in enumerate(ideal))
    expected = set(case.expected_warnings)
    # Warnings are evaluated in the first 50 returned fragments, the same retrieval budget as recall.
    found = {
        warning
        for key in keys[:50]
        if key in labels and labels[key].grade > 0
        for warning in labels[key].warning_ids
    }
    return {
        "id": case.id,
        "kind": case.kind,
        "recall_at_50": len(set(keys[:50]) & relevant) / len(relevant),
        "ndcg_at_10": dcg / idcg if idcg else 0.0,
        "false_positives_at_10": sum(key in labels and labels[key].grade == 0 for key in keys[:10]),
        "unjudged_at_10": sum(key not in labels for key in keys[:10]),
        "warning_coverage_at_50": len(found & expected) / len(expected) if expected else None,
        "relevant_total": len(relevant),
        "expected_warnings_total": len(expected),
    }


def evaluate(
    suite: ContentSuite,
    rankings: Mapping[str, Sequence[FragmentKey]],
    corpus: Sequence[FragmentKey],
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    validate_fragments(suite, corpus)
    if set(rankings) != {case.id for case in suite.cases}:
        raise ValueError("rankings must contain exactly the case IDs")
    known = {key.identity for key in corpus}
    if any(key.identity not in known for ranked in rankings.values() for key in ranked):
        raise ValueError("rankings contain fragments outside the evaluated corpus")
    rows = [metrics(case, rankings[case.id]) for case in suite.cases]
    metric_names = (
        "recall_at_50",
        "ndcg_at_10",
        "false_positives_at_10",
        "unjudged_at_10",
        "warning_coverage_at_50",
    )
    summary: dict[str, Any] = {"cases": len(rows)}
    for name in metric_names:
        values = [row[name] for row in rows if row[name] is not None]
        summary[name] = sum(values) / len(values) if values else None
    return {
        "metadata": {
            **metadata,
            "cases_hash": fingerprint(suite.model_dump()),
            "corpus_hash": fingerprint(sorted(known)),
            "metric_version": 1,
        },
        "summary": summary,
        "cases": rows,
    }


def compare(baseline: Mapping[str, Any], current: Mapping[str, Any]) -> list[str]:
    """No metric degradation per case; a rebuild may change generation, not content."""
    required = (
        "cases_hash",
        "corpus_hash",
        "model_name",
        "passage_profile",
        "text_repr_version",
        "dictionary_fingerprint",
        "signals",
        "metric_version",
        "evaluation_mode",
    )
    for name in required:
        if name not in baseline["metadata"] or name not in current["metadata"]:
            raise ValueError(f"missing comparison metadata: {name}")
        if baseline["metadata"][name] != current["metadata"][name]:
            raise ValueError(f"incomparable baseline: {name} differs")
    before = {row["id"]: row for row in baseline["cases"]}
    after = {row["id"]: row for row in current["cases"]}
    if before.keys() != after.keys():
        raise ValueError("baseline case IDs differ")
    regressions = []
    directions = {
        "recall_at_50": 1,
        "ndcg_at_10": 1,
        "warning_coverage_at_50": 1,
        "false_positives_at_10": -1,
        "unjudged_at_10": -1,
    }
    for key, row in after.items():
        for metric, direction in directions.items():
            old, new = before[key][metric], row[metric]
            if old is None and new is None:
                continue
            if old is None or new is None or direction * (new - old) < -1e-12:
                regressions.append(f"{key}:{metric}")
    return regressions
