"""Project warnings locally from existing rules and validated model responses; never infer."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Literal

from backend.ai.herb_association_classification import Work, relation_id
from backend.ai.herb_association_rules import Decision, classify_rule, scoped_warning
from backend.ai.herb_association_scope import LocalConditionScope
from backend.ai.herb_index_catalog import normalize_herb_name

PROJECTION_VERSION = 2
WarningKind = Literal["prohibition", "precaution", "none", "unknown"]
WARNING_KINDS = ("prohibition", "precaution", "none", "unknown")


@dataclass(frozen=True)
class CautionDecision:
    warning_kind: WarningKind
    has_recommendation: bool
    origin: Literal["rule", "model"]
    rule_code: str
    quotes: tuple[tuple[int, int], ...] = ()


# Positive validation already checked the booleans, candidate identities and local disease scope.
def model_projections(
    raw: dict[str, Any], batch: list[Work], validated: dict[str, Decision]
) -> dict[str, CautionDecision]:
    result = {}
    for position, work in enumerate(batch):
        identifier = relation_id(work)
        decision = validated[identifier]
        entry = raw["relations"][f"r{position}"]
        kind: WarningKind = "unknown"
        if decision.label != "unclear":
            kind = "prohibition" if entry["prohibition"] else "none"
        elif not entry["prohibition"]:
            # No warning was asserted; an unsupported positive claim is never transferred.
            kind = "none"
        result[identifier] = CautionDecision(
            kind, decision.label == "positive", "model", "existing_model_response", decision.quotes
        )
    return result


# This projection cannot promote a locally resolved candidate into the model request queue.
def local_projection(originals: tuple[Work, ...]) -> CautionDecision:
    decisions: list[CautionDecision] = []
    complete = True
    for unit, candidate in originals:
        decision = classify_rule(unit, candidate)
        complete = complete and decision is not None
        for existing in (decision, scoped_warning(unit, candidate)):
            if existing is None:
                continue
            kind: WarningKind = "none"
            if existing.label in {"caution", "mixed"}:
                passages = "\n".join(unit.text[a:b] for a, b in existing.quotes)
                context = normalize_herb_name("\n".join((*unit.headings, passages)))
                limited = re.search(
                    r"\b(doza|doze|mg|mcg|zilnic|sarcina|copii|gravide|daca|numai|doar)\b|"
                    r"\b(?:consultati|intrebati|supraveghere|sfatul)\b",
                    context,
                )
                negated = re.search(
                    r"\bnu (?:e|este|sunt) (?:interzis\w*|contraindicat\w*)\b", context
                )
                prohibited = re.search(
                    r"\b(interzis\w*|contraindicat\w*|de evitat|nu se recomanda|"
                    r"se recomanda evitarea|nu (?:este|sunt) recomandat\w*|evitati|eliminati|"
                    r"nu (?:consumati|folositi|luati|mancati)|nu este permis)\b",
                    context,
                )
                kind = (
                    "prohibition"
                    if existing.rule == "explicit_consumption_prohibition_v3"
                    or (prohibited and not limited and not negated)
                    else "unknown"
                    if negated
                    else "precaution"
                )
            elif existing.label == "unclear":
                kind = "unknown"
            decisions.append(
                CautionDecision(
                    kind,
                    existing.label in {"positive", "mixed"},
                    "rule",
                    existing.rule,
                    tuple((a + unit.start, b + unit.start) for a, b in existing.quotes),
                )
            )
    if not complete:
        # Locally recognized warnings are authoritative; absence requires an evaluated model result.
        decisions = [d for d in decisions if d.warning_kind in {"prohibition", "precaution"}]
    return combine_projections(decisions)


# Explicit food/product lists may wrap across OCR lines and exceed the original rule templates.
# A warning about another procedure in the same fragment is never evidence about this product.
def list_prohibition(
    work: Work,
    *,
    scope_catalog: LocalConditionScope,
    condition_name: str,
    condition_synonyms: tuple[str, ...] = (),
) -> CautionDecision:
    unit, candidate = work
    for sentence in re.finditer(r"[^.!?;]+(?:[.!?;]|$)", unit.text):
        start, end = sentence.span()
        heading_prefix = re.match(r"^\s*(?:#{1,6}[ \t]+[^\n]*\n\s*)+", unit.text[start:end])
        if heading_prefix is not None:
            start += heading_prefix.end()
        mentions = tuple(
            (a, b)
            for a, b in candidate.mentions or (candidate.mention,)
            if start <= a < b <= end
            and not any(
                other.herb_id != candidate.herb_id and other.mention == (a, b)
                for other in unit.candidates
            )
        )
        if not mentions:
            continue
        # The product must be an object of avoidance, not a remedy for something to avoid.
        mentions = tuple(
            (a, b)
            for a, b in mentions
            if re.search(r"[,:]\s*(?:(?:si|și|şi|sau)\s+)?$", unit.text[start:a], re.I)
            or normalize_herb_name(unit.text[start:a])
            in {
                "evitati",
                "eliminati",
                "nu consumati",
                "nu mancati",
                "nu folositi",
                "nu luati",
                "q nu consumati",
                "q nu mancati",
                "q nu folositi",
                "q nu luati",
            }
        )
        if not mentions:
            continue
        # Analysis-only normalization leaves all persisted source offsets and text unchanged.
        statement = normalize_herb_name(
            re.sub(r"(?<=\w)-[ \t]*\r?\n\s*(?=\w)", "", unit.text[start:end])
        )
        statement = re.sub(r"^[^\w]+", "", statement)
        statement = re.sub(r"^(?:[qoui0-9]+\s+)+", "", statement)
        command = re.match(
            r"^(?:evitati|eliminati|nu (?:consumati|mancati|folositi|luati))\b|"
            r"^(?:alimente|plante|produse)(?:le)? (?:care )?"
            r"(?:trebuie (?:evitate|eliminate)|interzise|contraindicate|de evitat)\b",
            statement,
        )
        restricted = re.search(
            r"\b(dar|insa|except\w*|numai|doar|daca|impreuna|doza|doze|mg|mcg|"
            r"sarcina|gravide|copii|inainte|dupa|deoarece|fiindca|recomand\w*|"
            r"benefic\w*|util\w*|salutar\w*|prefer\w*|ajut\w*)\b|\bin (?:schimb|loc)\b",
            statement,
        )
        # A bare food name may also be a disease alias; only an explicit disease target
        # redirects the instruction away from the independently verified section scope.
        foreign_condition = any(
            identifier != candidate.condition_id
            and start <= a < b <= end
            and re.search(
                r"\b(?:in|la|pentru|contra|impotriva|caz de|cazul|"
                r"(?:persoan\w*|pacient\w*) cu)\s*$",
                normalize_herb_name(unit.text[max(start, a - 80) : a]),
            )
            for identifier, (a, b) in unit.condition_mentions
        )
        if command is None or restricted or foreign_condition:
            continue
        scoped_candidate = replace(candidate, mention=mentions[0], mentions=mentions)
        if any(
            scope_catalog.verifies(unit, scoped_candidate, name, None, (start, end))
            for name in (condition_name, *condition_synonyms)
        ):
            return CautionDecision(
                "prohibition",
                False,
                "rule",
                "explicit_product_avoidance_list_v2",
                ((unit.start + start, unit.start + end),),
            )
    return CautionDecision("unknown", False, "rule", "no_explicit_product_prohibition")


def combine_projections(decisions: list[CautionDecision]) -> CautionDecision:
    for kind in ("prohibition", "precaution", "none", "unknown"):
        selected = next((d for d in decisions if d.warning_kind == kind), None)
        if selected is not None:
            return CautionDecision(
                selected.warning_kind,
                any(d.has_recommendation for d in decisions),
                selected.origin,
                selected.rule_code,
                selected.quotes,
            )
    return CautionDecision("unknown", False, "rule", "historical_unknown")


# A model warning can refer to a different product or procedure in the same full fragment.
# Only the independently scoped local evidence can corroborate an explicit prohibition.
def corroborate_projection(model: CautionDecision, local: CautionDecision) -> CautionDecision:
    if model.warning_kind == "prohibition" and local.warning_kind != "prohibition":
        unsupported = CautionDecision(
            "unknown",
            model.has_recommendation or local.has_recommendation,
            model.origin,
            "unverified_model_prohibition",
            model.quotes,
        )
        if local.warning_kind == "precaution":
            return combine_projections([unsupported, local])
        return unsupported
    return combine_projections([model, local])


def decode_projection(value: dict[str, Any]) -> CautionDecision:
    if (
        value.get("warning_kind") not in WARNING_KINDS
        or type(value.get("has_recommendation")) is not bool
        or value.get("origin") not in {"rule", "model"}
        or not isinstance(value.get("rule_code"), str)
        or not isinstance(value.get("quotes"), list)
    ):
        raise ValueError("CAUTION_INVALID_CACHE")
    quotes = []
    for span in value["quotes"]:
        if (
            not isinstance(span, list)
            or len(span) != 2
            or any(type(n) is not int for n in span)
            or not 0 <= span[0] < span[1]
        ):
            raise ValueError("CAUTION_INVALID_CACHE")
        quotes.append(tuple(span))
    return CautionDecision(
        value["warning_kind"],
        value["has_recommendation"],
        value["origin"],
        value["rule_code"],
        tuple(quotes),
    )
