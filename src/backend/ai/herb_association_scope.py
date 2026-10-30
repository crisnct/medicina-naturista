"""Verify local disease identities and source boundaries without fuzzy equivalence."""

from __future__ import annotations

import re
from bisect import bisect_right
from collections import OrderedDict

from backend.ai.conditions import ConditionDictionary, make_condition
from backend.ai.herb_association_rules import Candidate, Unit
from backend.ai.herb_index_catalog import normalize_herb_name

# Generic treatment subsections inherit their disease; a new disease closes that scope.
_SUBSECTION = re.compile(
    r"^(?:internal use|external use|treatment|recommendations|herbs|administration|dosage|preparation|diet|nutrition|foods|remedies|recipes|warnings|precautions|contraindications|uz intern|uz extern|tratament|recomandari|plante|administrare|dozare|doze|"
    r"mod de preparare|preparare|dieta|nutritie|nutrienti|suplimente|alimente|remedii|"
    r"retete|preparate|atentionari|precautii|contraindicatii)\b"
)
_CLINICAL_HEADING = re.compile(
    r"^(?:conditions|diseases|disorders|afectiuni|boli|boala|tulburari|maladii)\b"
)
# OCR can leave one or two short carry-over words before an otherwise clinical title.
_OCR_HEADING = re.compile(r"(?:[a-zăâîșț]+[-\s]+){1,2}[A-ZĂÂÎȘȚ][A-ZĂÂÎȘȚ \t-]{3,}")
_INSTRUCTION = re.compile(
    r"\b(?:use|take|drink|contains|helps|capsules|teaspoons|se|sunt|este|are|ajuta|contine|bea|folos\w*|utiliz\w*|infuz\w*|"
    r"lingur\w*|capsul\w*|mg|ml|tinctur\w*|flori|frunze)\b"
)
_INTRODUCTION = re.compile(
    r"\b(?:[iî]n\s+)?(?:tratarea|tratamentul)\s+([^\n:;.()]{1,160})", re.IGNORECASE
)


class LocalConditionScope:
    # One catalog and boundary cache belong to one preparation worker, never global state.
    def __init__(self, conditions: dict[int, str], synonyms: dict[int, tuple[str, ...]]) -> None:
        self.identifiers = {name: identifier for identifier, name in conditions.items()}
        self._acronyms: dict[str, set[int]] = {}
        catalog = []
        for identifier, name in conditions.items():
            condition = make_condition(name, synonyms.get(identifier, ()))
            aliases = []
            for term in condition.terms[1:]:
                # Acronyms must retain case: Romanian "pe" is not the catalog alias "PE".
                if len(term) > 1 and term.isalpha() and term.isupper():
                    self._acronyms.setdefault(term, set()).add(identifier)
                else:
                    aliases.append(term)
            catalog.append(make_condition(condition.name, aliases))
        self.dictionary = ConditionDictionary(catalog)
        self._boundaries: OrderedDict[tuple[str, str], tuple[tuple[int, frozenset[int]], ...]] = (
            OrderedDict()
        )

    def resolve(self, text: str) -> frozenset[int]:
        identifiers = {self.identifiers[item.name] for item in self.dictionary.find(text)}
        for token in re.findall(r"[^\W_]+", text, flags=re.UNICODE):
            identifiers.update(self._acronyms.get(token, ()))
        return frozenset(identifiers)

    def boundaries(self, unit: Unit) -> tuple[tuple[int, frozenset[int]], ...]:
        key = (unit.identity, unit.text)
        if key in self._boundaries:
            self._boundaries.move_to_end(key)
            return self._boundaries[key]
        markers: dict[int, frozenset[int]] = {0: frozenset()}
        offset = 0
        lines = unit.text.splitlines(keepends=True)
        for index, line in enumerate(lines):
            stripped = line.strip()
            markdown = re.match(r"^#{1,6}\s+", stripped)
            heading = re.sub(r"\{[^}]*\}", "", stripped)
            heading = re.sub(r"^[#\s*\[\]]+|[\s*\[\]]+$", "", heading)
            plain = normalize_herb_name(heading)
            resolved = self.resolve(heading)
            listed = re.match(r"^(?:\\?[-+*]\s|\d+[.)]\\?\s|[|])", stripped)
            isolated = (index == 0 or not lines[index - 1].strip()) and (
                index + 1 == len(lines) or not lines[index + 1].strip()
            )
            short = (
                0 < len(heading) <= 120
                and len(plain.split()) <= 12
                and not listed
                and not _INSTRUCTION.search(plain)
                and not re.search(r"[;!?]", heading)
                and (
                    isolated
                    or heading.isupper()
                    or _CLINICAL_HEADING.search(plain)
                    or _OCR_HEADING.fullmatch(heading)
                )
            )
            if markdown or (short and (resolved or _CLINICAL_HEADING.search(plain))):
                if resolved or not _SUBSECTION.search(plain):
                    markers[offset] = resolved
            offset += len(line)
        for match in _INTRODUCTION.finditer(unit.text):
            markers[match.start()] = self.resolve(match[1])
        merged: list[tuple[int, frozenset[int]]] = []
        for position, diseases in sorted(markers.items()):
            if diseases and merged and diseases == merged[-1][1]:
                continue
            merged.append((position, diseases))
        result = tuple(merged)
        self._boundaries[key] = result
        if len(self._boundaries) > 128:
            self._boundaries.popitem(last=False)
        return result

    def verifies(
        self,
        unit: Unit,
        candidate: Candidate,
        local_condition: str,
        scope_quote: tuple[int, int] | None,
        evidence_quote: tuple[int, int],
    ) -> bool:
        resolved = self.resolve(local_condition)
        if resolved and candidate.condition_id not in resolved:
            return False
        # A shared ambiguous alias is not proof that catalog identities are equivalent.
        if len(resolved) > 1 and not re.search(r",|;|/|\b(?:si|sau)\b", local_condition):
            return False
        evidence_start, evidence_end = evidence_quote
        positions: list[int] = []
        if resolved and local_condition.strip():
            if scope_quote is not None:
                start, end = scope_quote
                positions = [
                    start + m.start()
                    for m in re.finditer(
                        re.escape(local_condition.strip()), unit.text[start:end], re.IGNORECASE
                    )
                ]
            # Recover missing wire references only from the unchanged source itself.
            if not positions:
                positions = [
                    m.start()
                    for m in re.finditer(
                        re.escape(local_condition.strip()), unit.text, re.IGNORECASE
                    )
                ]
        boundaries = self.boundaries(unit)
        starts = [start for start, _ in boundaries]
        for a, b in candidate.mentions or (candidate.mention,):
            # The evidence must name this product, not another recommendation nearby.
            if not (a < evidence_end and b > evidence_start):
                continue
            anchor = bisect_right(starts, a) - 1
            # An unambiguous source heading/intro is stronger than a missing model name.
            if boundaries[anchor][1] == {candidate.condition_id}:
                return True
            for position in positions:
                if bisect_right(starts, position) - 1 != anchor:
                    continue
                governing = boundaries[anchor][1]
                if not governing or candidate.condition_id in governing:
                    return True
                # An explicit disease in the same sentence can override a parent heading.
                lo, hi = sorted((position, a))
                if not re.search(r"[.!?;\n]", unit.text[lo:hi]):
                    return True
        return False
