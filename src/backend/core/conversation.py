"""Conversation orchestration, independent of FastAPI and frontend modules."""

from __future__ import annotations

import copy
import logging
import re
import secrets
from dataclasses import dataclass, replace
from typing import Any

from backend.ai.categories import category_selection
from backend.ai.client import AIUnavailable
from backend.ai.condition_ai import resolved_for
from backend.ai.conditions import ResolvedQuery, resolve_query
from backend.ai.report_validation import ValidatedReport, validate_report
from backend.ai.search import ALL_SIGNALS, SearchSignals
from backend.config import Settings
from backend.core.contracts import (
    AIProtocol,
    EmailProtocol,
    Evidence,
    IdentifyCondition,
    RenderPDF,
    RetrievalProtocol,
)
from backend.core.errors import ApplicationError, OperationCancelled
from backend.core.models import (
    CommitChange,
    OperationResult,
    PendingSearch,
    SessionData,
    SessionOperation,
    StoredReport,
)
from backend.core.operation_context import OperationBudget, operation_budget
from backend.core.sessions import SessionStore
from backend.integrations.gmail import EMAIL_SKIPPED
from backend.reporting.chat import (
    download_message,
    fragments_message,
    generate_message,
    recommendation_text,
    report_filename,
)
from backend.reporting.chat import text as text_message

logger = logging.getLogger("naturist.conversation")

NO_FRAGMENT_ABOVE_MIN_SCORE = (
    "Niciun fragment nu atinge scorul minim selectat. Alegeți un prag mai mic."
)
WELCOME = "Bună ziua! 👋"
NO_CATEGORY_SELECTED_MESSAGE = "Nicio sursă selectată. Bifați cel puțin o categorie în panoul „Căutare avansată” înainte de căutare."
CONDITION_AI_NOTICE = "🤖 Nu am găsit afecțiunea în dicționarul meu. Încerc să o identific cu ajutorul AI. Vă rog să așteptați."
CONDITION_NOT_IDENTIFIED_MESSAGE = "⚠️ Nu am putut identifica afecțiunea din mesaj."
CONDITION_NOT_IDENTIFIED_CONTINUES = (
    f"{CONDITION_NOT_IDENTIFIED_MESSAGE} Caut după textul mesajului."
)
CONDITION_NOT_IDENTIFIED_STOPS = (
    f"{CONDITION_NOT_IDENTIFIED_MESSAGE} Scrieți denumirea afecțiunii (ex. gripă, hipertensiune)."
)
EMAIL_OFFER = (
    "Dacă doriți să trimiteți documentul pe mail la cineva, spuneți-mi la ce adresă să îl trimit."
)
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


# Documents the given category ids actually cover, for the "Caut rapid în
# cele N documente" notice — the whole corpus (retriever.document_count) when
# the index has no category tree (nothing to restrict by), otherwise the sum
# of each selected category's own_documents (never total_documents, which
# would double-count a folder together with its own subfolders if both ended
# up selected). An id outside the known set (stale, or no tree at all) is
# simply not counted, same as everywhere else category ids are consumed.
def document_count_for_categories(category_ids: set[str], retriever) -> int:
    tree = getattr(retriever, "category_tree", None)
    if tree is None:
        return getattr(retriever, "document_count", 0)
    known = tree.known_ids()
    return sum(
        tree.nodes[category_id].own_documents
        for category_id in category_ids
        if category_id in known
    )


# Whether the message goes to the condition AI: the conditions signal is on, a
# backend is configured and the dictionary names no condition in any segment.
def needs_condition_ai(health_problem: str, signals: SearchSignals, settings: Settings) -> bool:
    return bool(
        signals.conditions
        and settings.condition_ai_backends
        and not resolve_query(health_problem).conditions
    )


# Build the "Caut rapid în cele N documente" notice for the categories
# currently selected on the session.
def report_started_message(session, retriever) -> dict:
    count = document_count_for_categories(session.selected_categories, retriever)
    return text_message(
        "assistant",
        f"🔍 Caut rapid în cele {count} documente interne disponibile. Vă rog să așteptați.",
    )


# Chat notice naming the condition(s) the health problem was recognised as in
# the condition dictionary (the same resolution rank() runs, so every
# comma-separated expression counts). With the conditions signal on, every
# recognised condition is named; the part "O caut și după denumirile: …" lists
# its synonyms and is there only with the lexical signal on, and only for a
# condition that is a whole expression of the message (an exact term or a
# near-identical spelling of one) — the only case in which the lexical search
# uses the synonyms (see ai/search.py's lexical_queries()). With the lexical
# signal alone, only those conditions are named; with neither, nothing is.
# None when nothing is to be named. `health_problem` is the typed text, or the
# message already resolved (dictionary plus AI conditions, see resolved_for());
# `by_ai` marks the conditions as identified by the AI rather than the dictionary.
def condition_identified_message(
    health_problem: str | ResolvedQuery,
    signals: SearchSignals = ALL_SIGNALS,
    by_ai: bool = False,
) -> dict | None:
    resolved = (
        health_problem
        if isinstance(health_problem, ResolvedQuery)
        else resolve_query(health_problem)
    )
    whole = {
        condition.name
        for segment in resolved.segments
        if segment.whole_condition
        for condition in segment.conditions
    }
    if signals.conditions:
        conditions = resolved.conditions
    elif signals.lexical:
        conditions = tuple(
            condition for condition in resolved.conditions if condition.name in whole
        )
    else:
        return None
    if not conditions:
        return None
    lines = []
    for condition in conditions:
        label = (
            "Am identificat afecțiunea (cu ajutorul AI)" if by_ai else "Am identificat afecțiunea"
        )
        line = f"✅ {label}: **{condition.name}**."
        if signals.lexical and condition.name in whole and len(condition.terms) > 1:
            line += f" O caut și după denumirile: {', '.join(condition.terms[1:])}."
        lines.append(line)
    return text_message("assistant", "\n".join(lines))


def evidence_above(evidence: Evidence, min_score: float) -> Evidence:
    return {
        eid: item
        for eid, item in evidence.items()
        if min_score <= 0 or (item.get("relevance_percent") or 0) >= min_score
    }


def cancelled(**extra: Any) -> dict[str, Any]:
    return {**OperationResult(cancelled=True).as_dict(), **extra}


@dataclass
class ConversationService:
    settings: Settings
    store: SessionStore
    retriever: RetrievalProtocol
    ai: AIProtocol
    identify: IdentifyCondition
    email: EmailProtocol
    pdf: RenderPDF

    def budget(self, operation: SessionOperation) -> OperationBudget:
        return OperationBudget(
            operation.deadline, self.store.clock, lambda: self.store.checkpoint(operation)
        )

    def close(self, cookie_id: str, tab_id: str) -> dict[str, Any]:
        self.store.delete(cookie_id, tab_id)
        return {
            "messages": [
                text_message(
                    "assistant",
                    "Sesiunea a fost închisă. Reîncărcați pagina pentru o conversație nouă.",
                )
            ]
        }

    def deliver_email(self, operation: SessionOperation, address: str) -> OperationResult:
        self.store.checkpoint(operation)
        report = operation.snapshot.report
        assert report is not None
        try:
            with operation_budget(self.budget(operation)):
                status = self.email(report.health_problem, report.data, report.filename, address)
            reply = (
                "Trimiterea pe mail nu este configurată momentan."
                if status == EMAIL_SKIPPED
                else f"✅ Am trimis documentul la {address}."
            )
        except OperationCancelled:
            raise
        except Exception as exc:
            logger.error("report_stage_failed stage=email type=%s", type(exc).__name__)
            reply = "Nu am putut trimite documentul pe mail. Încercați din nou."
        return self.store.commit_operation(
            operation,
            CommitChange(
                messages=[text_message("user", address), text_message("assistant", reply)]
            ),
        )

    def message(
        self, session: SessionData, message: str, categories: set[str], signals: SearchSignals
    ) -> dict[str, Any]:
        message = message.strip()
        if not message:
            return {
                **OperationResult().as_dict(),
                "startSearch": False,
                "identifyCondition": False,
            }
        if len(message) > self.settings.max_chat_chars:
            raise ApplicationError(
                "MESSAGE_TOO_LONG",
                f"Mesajul depășește limita de {self.settings.max_chat_chars} caractere.",
                422,
            )
        # The report is selected by the registry, never read across an external call.
        kind = "email" if EMAIL_PATTERN.fullmatch(message) else "message"
        operation = self.store.begin_operation(session, kind)
        try:
            snapshot = operation.snapshot
            if kind == "email" and snapshot.report:
                result = self.deliver_email(operation, message)
                return {
                    **result.as_dict(),
                    "startSearch": False,
                    "identifyCondition": False,
                }
            if kind == "email":
                # An address without a report remains ordinary chat text.
                self.store.finish_operation(operation)
                operation = self.store.begin_operation(session, "message")
                snapshot = operation.snapshot
            profile = snapshot.profile
            profile.replace_health_problem(message)
            categories = set(categories)
            messages = [text_message("user", message)]
            start_search, identify = True, False
            if getattr(self.retriever, "category_tree", None) is not None and not categories:
                messages.append(text_message("assistant", NO_CATEGORY_SELECTED_MESSAGE))
                start_search = False
            elif needs_condition_ai(profile.health_problem, signals, self.settings):
                messages.append(text_message("assistant", CONDITION_AI_NOTICE))
                identify = True
            else:
                identified = condition_identified_message(profile.health_problem, signals)
                if identified:
                    messages.append(identified)
                count = document_count_for_categories(categories, self.retriever)
                messages.append(
                    text_message(
                        "assistant",
                        f"🔍 Caut rapid în cele {count} documente interne disponibile. Vă rog să așteptați.",
                    )
                )
            result = self.store.commit_operation(
                operation, CommitChange(messages, profile, True, categories, signals)
            )
            if not result.cancelled:
                logger.info(
                    "user_message_accepted chars=%s selected_categories=%s signals=%s",
                    len(message),
                    len(categories),
                    signals.code,
                )
            return {
                **result.as_dict(),
                "startSearch": start_search and not result.cancelled,
                "identifyCondition": identify and not result.cancelled,
                "contextRevision": snapshot.context_revision + 1,
            }
        except OperationCancelled:
            return cancelled(startSearch=False, identifyCondition=False)
        finally:
            self.store.finish_operation(operation)

    def condition(
        self, session: SessionData, expected_revision: int | None = None
    ) -> dict[str, Any]:
        try:
            operation = self.store.begin_operation(
                session, "condition", expected_revision=expected_revision
            )
        except OperationCancelled:
            return cancelled(startSearch=False)
        try:
            snapshot = operation.snapshot
            if not needs_condition_ai(
                snapshot.profile.health_problem, snapshot.search_signals, self.settings
            ):
                self.store.checkpoint(operation)
                return {**OperationResult().as_dict(), "startSearch": True}
            self.store.checkpoint(operation)
            with operation_budget(self.budget(operation)):
                result = self.identify(resolve_query(snapshot.profile.health_problem))
            self.store.checkpoint(operation)
            profile = snapshot.profile
            profile.ai_conditions = copy.deepcopy(result.answers)
            messages, start_search = [], True
            if result.identified:
                identified = condition_identified_message(
                    resolved_for(profile), snapshot.search_signals, by_ai=True
                )
                if identified:
                    messages.append(identified)
            elif not (snapshot.search_signals.lexical or snapshot.search_signals.semantic):
                messages.append(text_message("assistant", CONDITION_NOT_IDENTIFIED_STOPS))
                start_search = False
            else:
                messages.append(text_message("assistant", CONDITION_NOT_IDENTIFIED_CONTINUES))
            if start_search:
                messages.append(report_started_message(snapshot, self.retriever))
            committed = self.store.commit_operation(
                operation, CommitChange(messages=messages, profile=profile)
            )
            return {
                **committed.as_dict(),
                "startSearch": start_search and not committed.cancelled,
            }
        except OperationCancelled:
            return cancelled(startSearch=False)
        finally:
            self.store.finish_operation(operation)

    def search(self, session: SessionData, expected_revision: int | None = None) -> dict[str, Any]:
        try:
            operation = self.store.begin_operation(
                session, "search", expected_revision=expected_revision
            )
        except OperationCancelled:
            return cancelled()
        try:
            snapshot = operation.snapshot
            tree = getattr(self.retriever, "category_tree", None)
            if tree is not None:
                # Validate even when an unresolved A-only query exits before collect().
                category_selection(snapshot.selected_categories, tree)
            signals = snapshot.search_signals
            if (
                signals.conditions
                and not (signals.lexical or signals.semantic)
                and not resolved_for(snapshot.profile).conditions
            ):
                return self.store.commit_operation(
                    operation,
                    CommitChange(
                        messages=[text_message("assistant", CONDITION_NOT_IDENTIFIED_STOPS)]
                    ),
                ).as_dict()
            self.store.checkpoint(operation)
            with operation_budget(self.budget(operation)):
                evidence = self.retriever.collect(snapshot, self.ai.context_budget())
            self.store.checkpoint(operation)
            if not evidence:
                committed = self.store.commit_operation(
                    operation,
                    CommitChange(
                        messages=[
                            text_message(
                                "assistant",
                                "Nu am găsit fragmente relevante în sursele locale. Încercați o căutare semantică sau introduceți altă denumire a afecțiunii.",
                            )
                        ]
                    ),
                ).as_dict()
                return {
                    **committed,
                    "indexGeneration": getattr(evidence, "index_generation", None),
                    "removedCategoryIds": getattr(evidence, "removed_category_ids", []),
                }
            search_id = secrets.token_hex(6)
            committed = self.store.commit_operation(
                operation,
                CommitChange(
                    messages=[
                        fragments_message(search_id, evidence, signals),
                        generate_message(search_id),
                    ],
                    search=(
                        search_id,
                        PendingSearch(
                            profile=snapshot.profile.as_dict(),
                            evidence=dict(evidence),
                            signals=signals,
                            index_generation=getattr(evidence, "index_generation", None),
                        ),
                    ),
                ),
            ).as_dict()
            return {
                **committed,
                "indexGeneration": getattr(evidence, "index_generation", None),
                "removedCategoryIds": getattr(evidence, "removed_category_ids", []),
            }
        except OperationCancelled:
            return cancelled()
        finally:
            self.store.finish_operation(operation)

    def generate(
        self, session: SessionData, search_id: str, min_score: float = 0
    ) -> OperationResult:
        operation = self.store.begin_operation(session, "generate", search_id=search_id)
        try:
            snapshot = operation.snapshot
            search = snapshot.search
            assert search is not None
            profile, evidence = search.profile, evidence_above(search.evidence, min_score)
            if not evidence:
                return self.store.commit_operation(
                    operation,
                    CommitChange(messages=[text_message("assistant", NO_FRAGMENT_ABOVE_MIN_SCORE)]),
                )
            self.store.checkpoint(operation)
            with operation_budget(self.budget(operation)):
                sections = self.ai.generate(profile, evidence)
            if not isinstance(sections, ValidatedReport):
                sections = validate_report(sections, evidence)
            self.store.checkpoint(operation)
            with operation_budget(self.budget(operation)):
                report = self.pdf(profile, sections, evidence, min_score)
            self.store.checkpoint(operation)
            report_id = secrets.token_urlsafe(18)
            filename = report_filename(snapshot, profile)
            messages = [
                text_message("assistant", recommendation_text(sections, evidence)),
                download_message(
                    snapshot, report_id, profile, prefix=self.settings.public_root_path
                ),
                text_message("assistant", EMAIL_OFFER),
            ]
            committed = self.store.commit_operation(
                operation,
                CommitChange(
                    messages=messages,
                    report=(
                        report_id,
                        StoredReport(report, filename, profile.get("health_problem", "")),
                    ),
                    replace_search_id=search_id,
                ),
            )
            if not committed.cancelled:
                committed = replace(
                    committed,
                    partial=sections.partial,
                    validation_warnings=[
                        warning.model_dump(exclude_none=True)
                        for warning in sections.validationWarnings
                    ],
                )
            return committed
        except OperationCancelled:
            return OperationResult(cancelled=True)
        except ApplicationError:
            raise
        except Exception as exc:
            logger.error("report_stage_failed stage=generate type=%s", type(exc).__name__)
            reply = (
                "Furnizorul AI nu este disponibil. Încercați din nou."
                if isinstance(exc, AIUnavailable)
                else "Raportul nu a putut fi generat. Încercați din nou."
            )
            return self.store.commit_operation(
                operation, CommitChange(messages=[text_message("assistant", reply)])
            )
        finally:
            self.store.finish_operation(operation)
