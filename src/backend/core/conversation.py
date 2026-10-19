"""Conversation orchestration, independent of FastAPI and frontend modules."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
import secrets
from dataclasses import dataclass, replace
from typing import Any

from backend.ai.categories import category_selection
from backend.ai.client import AIUnavailable
from backend.ai.condition_ai import catalog_condition_names, resolved_for
from backend.ai.conditions import ResolvedQuery, _normalize, resolve_query
from backend.ai.message_classification import MessageClassification
from backend.ai.report_validation import ValidatedReport, validate_report
from backend.ai.search import ALL_SIGNALS, SearchSignals
from backend.config import Settings
from backend.core.contracts import (
    AIProtocol,
    ClassifyMessage,
    EmailProtocol,
    Evidence,
    IdentifyCondition,
    ListTopHerbs,
    LookupHerb,
    RecordReportMetrics,
    RenderPDF,
    RetrievalProtocol,
)
from backend.core.errors import ApplicationError, OperationCancelled
from backend.core.models import (
    CommitChange,
    HealthProfile,
    MessageRouting,
    OperationResult,
    PendingSearch,
    SessionData,
    SessionOperation,
    StoredReport,
)
from backend.core.operation_context import OperationBudget, operation_budget
from backend.core.report_metrics import ReportMetrics, validate_min_score
from backend.core.sessions import SessionStore
from backend.integrations.gmail import EMAIL_SKIPPED, GmailAuthorizationError
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
WELCOME = "👋 Cu ce vă pot ajuta?"
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
DIVERSE_SIGNALS_MESSAGE = "Activați căutarea lexicală sau semantică în panoul „Căutare avansată” pentru a căuta după mesaj."
GENERAL_QUESTION_NOTICE = "💬 Am identificat o întrebare generală."
CLASSIFICATION_UNAVAILABLE = (
    "Clasificarea AI nu este disponibilă momentan. Continui cu fluxul de căutare existent."
)


def email_candidates(message: str) -> list[str]:
    tokens = re.split(r"[\s<>;,()]+", message)
    result = []
    for token in tokens:
        address = token.strip(".!?:\"'")
        if not EMAIL_PATTERN.fullmatch(address) or len(address) > 254:
            continue
        local, domain = address.rsplit("@", 1)
        if len(local) > 64 or local.startswith(".") or local.endswith(".") or ".." in local:
            continue
        if any(
            len(label) > 63 or label.startswith("-") or label.endswith("-")
            for label in domain.split(".")
        ):
            continue
        result.append(address)
    return list(dict.fromkeys(result))


def email_request_hint(message: str) -> bool:
    normalized = _normalize(message)
    return bool(EMAIL_PATTERN.fullmatch(message)) or (
        bool(re.search(r"\b(trimite|trimiteti|trimiti|expediaza|send|email|mail)\b", normalized))
        and ("@" in message or any(word in normalized for word in ("raport", "document", "pdf")))
    )


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
# dictionary names no condition in any segment. Ollama is the only AI provider.
def needs_condition_ai(health_problem: str, signals: SearchSignals) -> bool:
    return bool(signals.conditions and not resolve_query(health_problem).conditions)


# Build the "Caut rapid în cele N documente" notice for the categories
# currently selected on the session.
def report_started_message(session, retriever) -> dict:
    count = document_count_for_categories(session.selected_categories, retriever)
    return text_message(
        "assistant",
        f"🔍 Caut rapid în cele **{count} documente** interne disponibile. Vă rog să așteptați.",
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


def evidence_within_budget(evidence: Evidence, max_chars: int | None) -> Evidence:
    if max_chars is None:
        return evidence
    selected: Evidence = {}
    used = 0
    for eid, item in sorted(
        evidence.items(), key=lambda entry: entry[1].get("score", float("-inf")), reverse=True
    ):
        size = len(item["text"])
        if used + size > max_chars:
            break
        selected[eid] = item
        used += size
    return selected


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
    classify_message: ClassifyMessage | None = None
    herb_lookup: LookupHerb | None = None
    top_herbs: ListTopHerbs | None = None
    report_model: str | None = None
    report_model_choice: str = ""
    report_ai_effort: str | None = None
    record_report_metrics: RecordReportMetrics | None = None

    def budget(self, operation: SessionOperation) -> OperationBudget:
        def batch_progress(completed: int, total: int, report: ValidatedReport | None) -> None:
            search = operation.snapshot.search
            assert search is not None
            preview = (
                recommendation_text(report, search.evidence, include_ready_message=False)
                if report is not None
                else None
            )
            self.store.generation_batch(operation, completed, total, preview)

        return OperationBudget(
            operation.deadline,
            self.store.clock,
            lambda: self.store.checkpoint(operation),
            (lambda text: self.store.generation_output(operation, text))
            if operation.kind == "generate"
            else None,
            report_thinking=(
                lambda text: self.store.generation_output(operation, text, thinking=True)
            )
            if operation.kind == "generate"
            else None,
            report_activity=(lambda event: self.store.generation_activity(operation, event))
            if operation.kind == "generate"
            else None,
            report_batch=batch_progress if operation.kind == "generate" else None,
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
        except GmailAuthorizationError:
            logger.error(
                "report_stage_failed stage=email type=GmailAuthorizationError oauth_error=invalid_grant"
            )
            reply = (
                "Autorizarea Gmail nu mai este validă. Administratorul trebuie să reautorizeze "
                "contul Google pentru trimiterea pe mail. Raportul rămâne disponibil pentru descărcare."
            )
        except Exception as exc:
            logger.error("report_stage_failed stage=email type=%s", type(exc).__name__)
            reply = "Nu am putut trimite documentul pe mail. Încercați din nou."
        return self.store.commit_operation(
            operation,
            CommitChange(messages=[text_message("assistant", reply)]),
        )

    def message(
        self,
        session: SessionData,
        message: str,
        categories: set[str],
        signals: SearchSignals,
        request_id: str | None = None,
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
        operation = self.store.begin_operation(session, "message")
        try:
            snapshot = operation.snapshot
            fingerprint = hashlib.sha256(
                json.dumps([message, sorted(categories), signals.code], ensure_ascii=False).encode(
                    "utf-8"
                )
            ).hexdigest()
            receipt = snapshot.message_receipts.get(request_id or "")
            if receipt is not None:
                revision, previous_fingerprint = receipt
                if previous_fingerprint != fingerprint:
                    raise ApplicationError(
                        "MESSAGE_ID_CONFLICT",
                        "Identificatorul mesajului a fost reutilizat pentru alt conținut.",
                        409,
                    )
                if revision != snapshot.context_revision:
                    return cancelled(
                        startSearch=False, identifyCondition=False, classifyMessage=False
                    )
                return {
                    **OperationResult().as_dict(),
                    "startSearch": False,
                    "identifyCondition": False,
                    "classifyMessage": True,
                    "contextRevision": revision,
                }
            previous = snapshot.routing
            routing = MessageRouting(
                message=message,
                clarification=previous.clarification,
                herb_choices=previous.herb_choices,
                report_id=(
                    previous.report_id
                    if previous.clarification == "email_raport"
                    else snapshot.report_id
                ),
            )
            result = self.store.commit_operation(
                operation,
                CommitChange(
                    messages=[text_message("user", message)],
                    new_context=True,
                    selected_categories=categories,
                    search_signals=signals,
                    routing=routing,
                    message_receipt=(request_id, fingerprint) if request_id else None,
                ),
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
                "startSearch": False,
                "identifyCondition": False,
                "classifyMessage": not result.cancelled,
                "contextRevision": snapshot.context_revision + 1,
            }
        except OperationCancelled:
            return cancelled(startSearch=False, identifyCondition=False, classifyMessage=False)
        finally:
            self.store.finish_operation(operation)

    def classify(
        self, session: SessionData, expected_revision: int | None = None
    ) -> dict[str, Any]:
        try:
            operation = self.store.begin_operation(
                session, "classify", expected_revision=expected_revision
            )
        except OperationCancelled:
            return cancelled(startSearch=False, identifyCondition=False)
        try:
            snapshot = operation.snapshot
            routing = snapshot.routing
            if not routing.message:
                raise ApplicationError("MESSAGE_UNAVAILABLE", "Trimiteți mai întâi un mesaj.", 409)
            if routing.classified:
                return {
                    **OperationResult().as_dict(),
                    "intent": routing.intent,
                    "startSearch": routing.start_search,
                    "identifyCondition": routing.identify_condition,
                    "contextRevision": snapshot.context_revision,
                }
            notices = []
            try:
                self.store.checkpoint(operation)
                with operation_budget(self.budget(operation)):
                    if self.classify_message is None:
                        raise AIUnavailable("Clasificatorul nu este configurat.")
                    decision = self.classify_message(
                        routing.message,
                        {
                            "report_available": routing.report_id is not None,
                            "pending_clarification": routing.clarification or None,
                            "herb_choices": list(routing.herb_choices),
                        },
                    )
            except OperationCancelled:
                raise
            except (AIUnavailable, ValueError) as exc:
                logger.warning(
                    "classification_fallback type=%s reason=%s",
                    type(exc).__name__,
                    getattr(exc, "reason", "invalid_output"),
                )
                if EMAIL_PATTERN.fullmatch(routing.message):
                    decision = MessageClassification(intent="email_raport")
                elif email_request_hint(routing.message) or routing.clarification == "email_raport":
                    decision = MessageClassification(
                        intent="email_raport", needs_clarification=True
                    )
                    notices.append(
                        text_message(
                            "assistant",
                            "Clasificarea nu este disponibilă. Reformulați cererea de trimitere și adresa destinatarului.",
                        )
                    )
                else:
                    decision = MessageClassification(intent="remedii")
                    notices.append(text_message("assistant", CLASSIFICATION_UNAVAILABLE))
            self.store.checkpoint(operation)
            # Preserve the existing address-only command, independent of a model decision.
            if EMAIL_PATTERN.fullmatch(routing.message):
                decision = MessageClassification(intent="email_raport")
            routing.intent = decision.intent
            routing.classified = True
            routing.clarification = ""
            routing.herb_choices = ()
            if decision.intent == "diverse" and not decision.needs_clarification:
                notices.append(text_message("assistant", GENERAL_QUESTION_NOTICE))
            if decision.intent == "email_raport":
                return self._route_email(operation, decision, notices)
            if decision.intent == "planta":
                return self._route_herb(operation, decision, notices)
            if decision.intent == "top_plante":
                return self._route_top_herbs(operation, decision, notices)
            if decision.intent == "remedii" and decision.needs_clarification:
                resolved = resolve_query(routing.message)
                # A condition-only reply already supplies the missing subject,
                # including spellings recognised by the retrieval dictionary.
                if resolved.segments and all(
                    segment.conditions and not segment.remainder for segment in resolved.segments
                ):
                    decision = decision.model_copy(update={"needs_clarification": False})
            if decision.needs_clarification:
                if decision.intent == "remedii":
                    routing.clarification = "remedii"
                    notices.append(
                        text_message(
                            "assistant",
                            "Pentru ce afecțiune sau problemă de sănătate doriți remedii?",
                        )
                    )
                    return self._commit_route(operation, notices)
                notices.append(
                    text_message(
                        "assistant",
                        "Precizați o singură solicitare: remedii, o plantă sau o întrebare generală.",
                    )
                )
                return self._commit_route(operation, notices)
            profile = snapshot.profile
            profile.replace_health_problem(routing.message)
            if (
                getattr(self.retriever, "category_tree", None) is not None
                and not snapshot.selected_categories
            ):
                notices.append(text_message("assistant", NO_CATEGORY_SELECTED_MESSAGE))
            elif decision.intent == "diverse" and not (
                snapshot.search_signals.lexical
                or snapshot.search_signals.semantic
                or resolve_query(routing.message).conditions
            ):
                notices.append(text_message("assistant", DIVERSE_SIGNALS_MESSAGE))
            else:
                routing.start_search = True
                routing.identify_condition = decision.intent == "remedii" and needs_condition_ai(
                    routing.message, snapshot.search_signals
                )
                if routing.identify_condition:
                    notices.append(text_message("assistant", CONDITION_AI_NOTICE))
                else:
                    if decision.intent == "remedii":
                        identified = condition_identified_message(
                            routing.message, snapshot.search_signals
                        )
                        if identified:
                            notices.append(identified)
                    notices.append(report_started_message(snapshot, self.retriever))
            return self._commit_route(operation, notices, profile)
        except OperationCancelled:
            return cancelled(startSearch=False, identifyCondition=False)
        finally:
            self.store.finish_operation(operation)

    def _commit_route(
        self,
        operation: SessionOperation,
        messages: list[dict[str, Any]],
        profile: HealthProfile | None = None,
    ) -> dict[str, Any]:
        routing = operation.snapshot.routing
        result = self.store.commit_operation(
            operation, CommitChange(messages=messages, profile=profile, routing=routing)
        )
        return {
            **result.as_dict(),
            "intent": routing.intent,
            "startSearch": routing.start_search and not result.cancelled,
            "identifyCondition": routing.identify_condition and not result.cancelled,
            "contextRevision": operation.snapshot.context_revision,
        }

    def _route_top_herbs(
        self,
        operation: SessionOperation,
        decision: MessageClassification,
        notices: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if decision.needs_clarification or decision.top_count is None:
            operation.snapshot.routing.clarification = "top_plante"
            notices.append(
                text_message(
                    "assistant", "Câte plante doriți în top? Precizați un număr între 1 și 10000."
                )
            )
        else:
            if self.top_herbs is None:
                raise ApplicationError(
                    "HERB_CATALOG_UNAVAILABLE", "Catalogul de plante nu este disponibil.", 503
                )
            with operation_budget(self.budget(operation)):
                herbs = self.top_herbs(decision.top_count)
            self.store.checkpoint(operation)
            if not herbs:
                content = "Catalogul nu conține plante pentru acest top."
            else:
                lines = [
                    f"### Top {len(herbs)} plante medicinale după numărul de afecțiuni "
                    "din catalog la care sunt utile"
                ]
                for position, herb in enumerate(herbs, 1):
                    aliases = (
                        f" (denumiri regionale: {', '.join(herb['ro_regional'])})"
                        if herb["ro_regional"]
                        else ""
                    )
                    conditions = "afecțiune" if herb["ranking"] == 1 else "afecțiuni"
                    name = herb["ro"][:1].upper() + herb["ro"][1:]
                    latin = herb["latin"].title()
                    lines.append(
                        f"{position}. **{name}** ({latin}) — utilă în "
                        f"{herb['ranking']} {conditions}{aliases}"
                    )
                content = "\n".join(lines)
            notices.append(text_message("assistant", content))
        return self._commit_route(operation, notices)

    def _route_herb(
        self,
        operation: SessionOperation,
        decision: MessageClassification,
        notices: list[dict[str, Any]],
    ) -> dict[str, Any]:
        routing = operation.snapshot.routing
        if decision.needs_clarification or not decision.herb_name:
            routing.clarification = "planta"
            notices.append(
                text_message(
                    "assistant",
                    "Despre ce plantă medicinală doriți informații? Precizați o singură plantă.",
                )
            )
        else:
            if self.herb_lookup is None:
                raise ApplicationError(
                    "HERB_CATALOG_UNAVAILABLE", "Catalogul de plante nu este disponibil.", 503
                )
            with operation_budget(self.budget(operation)):
                data = self.herb_lookup(decision.herb_name)
            self.store.checkpoint(operation)
            if data["status"] == "not_found":
                routing.clarification = "planta"
                notices.append(
                    text_message(
                        "assistant",
                        "Nu am găsit planta în catalog. Scrieți alt nume românesc sau denumirea latină.",
                    )
                )
            elif data["status"] == "ambiguous":
                routing.clarification = "planta"
                routing.herb_choices = tuple(data["choices"])
                notices.append(
                    text_message(
                        "assistant",
                        "Numele corespunde mai multor plante. Alegeți una: "
                        + ", ".join(routing.herb_choices)
                        + ".",
                    )
                )
            else:
                notices.append(
                    {
                        "kind": "herb_conditions",
                        "role": "assistant",
                        **{k: v for k, v in data.items() if k != "status"},
                    }
                )
        return self._commit_route(operation, notices)

    def _route_email(
        self,
        operation: SessionOperation,
        decision: MessageClassification,
        notices: list[dict[str, Any]],
    ) -> dict[str, Any]:
        routing = operation.snapshot.routing
        addresses = email_candidates(routing.message)
        # More '@' tokens than validated recipients includes malformed/multiple addresses.
        valid = len(addresses) == 1 and routing.message.count("@") == 1
        valid = valid and (decision.email_address is None or decision.email_address == addresses[0])
        if routing.report_id is None:
            notices.append(
                text_message(
                    "assistant",
                    "Nu există un raport precedent în această sesiune. Generați mai întâi un raport.",
                )
            )
        elif decision.needs_clarification or not valid:
            routing.clarification = "email_raport"
            notices.append(
                text_message(
                    "assistant",
                    "La ce adresă doriți să trimit raportul precedent? Precizați o singură adresă validă.",
                )
            )
        else:
            # Claim the message revision before the irreversible external call; retries never resend.
            routing.email_attempted = True
            result = self._commit_route(operation, notices)
            if result["cancelled"]:
                return result
            self.store.finish_operation(operation)
            email_operation = self.store.begin_operation(
                operation.session,
                "email",
                expected_revision=operation.snapshot.context_revision,
                report_id=routing.report_id,
            )
            try:
                if email_operation.snapshot.report is None:
                    delivered = self.store.commit_operation(
                        email_operation,
                        CommitChange(
                            messages=[
                                text_message(
                                    "assistant",
                                    "Raportul precedent nu mai este disponibil în sesiune. Generați din nou raportul.",
                                )
                            ]
                        ),
                    )
                else:
                    delivered = self.deliver_email(email_operation, addresses[0])
                result["messages"].extend(delivered.messages)
                for key in ("evictedSearchIds", "evictedReportIds", "evictedGroupIds"):
                    result[key].extend(delivered.as_dict()[key])
                result["cancelled"] = delivered.cancelled
                return result
            finally:
                self.store.finish_operation(email_operation)
        return self._commit_route(operation, notices)

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
            if snapshot.routing.message and (
                not snapshot.routing.classified or snapshot.routing.intent != "remedii"
            ):
                return {
                    **OperationResult().as_dict(),
                    "startSearch": snapshot.routing.intent == "diverse"
                    and snapshot.routing.start_search,
                }
            if not needs_condition_ai(snapshot.profile.health_problem, snapshot.search_signals):
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
            if snapshot.routing.message and (
                not snapshot.routing.classified
                or snapshot.routing.intent not in {"remedii", "diverse"}
                or not snapshot.routing.start_search
            ):
                raise ApplicationError(
                    "SEARCH_NOT_ALLOWED", "Acest mesaj nu pornește o căutare de fragmente.", 409
                )
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
                        messages=[
                            text_message(
                                "assistant",
                                DIVERSE_SIGNALS_MESSAGE
                                if snapshot.routing.intent == "diverse"
                                else CONDITION_NOT_IDENTIFIED_STOPS,
                            )
                        ]
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
                                "Nu am găsit fragmente relevante în sursele locale. Încercați o căutare semantică sau reformulați întrebarea."
                                if snapshot.routing.intent == "diverse"
                                else "Nu am găsit fragmente relevante în sursele locale. Încercați o căutare semantică sau introduceți altă denumire a afecțiunii.",
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
            search_intent = snapshot.routing.intent or "remedii"
            messages = [fragments_message(search_id, evidence, signals)]
            if search_intent == "remedii":
                messages.append(generate_message(search_id))
            committed = self.store.commit_operation(
                operation,
                CommitChange(
                    messages=messages,
                    search=(
                        search_id,
                        PendingSearch(
                            profile=snapshot.profile.as_dict(),
                            evidence=dict(evidence),
                            signals=signals,
                            index_generation=getattr(evidence, "index_generation", None),
                            intent=search_intent,
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
        self,
        session: SessionData,
        search_id: str,
        min_score: int = 0,
        *,
        admitted: SessionOperation | None = None,
    ) -> OperationResult:
        validate_min_score(min_score)
        generation_started_at = self.store.clock()
        operation = admitted or self.store.begin_operation(session, "generate", search_id=search_id)
        try:
            snapshot = operation.snapshot
            search = snapshot.search
            assert search is not None
            profile, evidence = search.profile, evidence_above(search.evidence, min_score)
            if not evidence:
                return self.store.commit_operation(
                    operation,
                    CommitChange(
                        messages=[
                            {
                                **text_message("assistant", NO_FRAGMENT_ABOVE_MIN_SCORE),
                                "generationSearchId": search_id,
                            }
                        ]
                    ),
                )
            self.store.generation_stage(operation, "generating")
            characters = sum(len(item["text"]) for item in evidence.values())
            with operation_budget(self.budget(operation)):
                sections = self.ai.generate(profile, evidence)
            self.store.generation_stage(operation, "validating")
            if not isinstance(sections, ValidatedReport):
                sections = validate_report(sections, evidence)
            self.store.generation_stage(operation, "rendering_pdf")
            with operation_budget(self.budget(operation)):
                report = self.pdf(profile, sections, evidence, min_score)
            self.store.generation_stage(operation, "publishing")
            self.store.checkpoint(operation)
            report_id = secrets.token_urlsafe(18)
            filename = report_filename(snapshot, profile)
            elapsed_seconds = max(0, int(self.store.clock() - generation_started_at))
            messages = [
                text_message(
                    "assistant",
                    recommendation_text(
                        sections,
                        evidence,
                        elapsed_seconds=elapsed_seconds,
                        ai_model=self.report_model,
                    ),
                ),
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
                    partial=sections.partial,
                    validation_warnings=[
                        warning.model_dump(exclude_none=True)
                        for warning in sections.validationWarnings
                    ][:32],
                ),
            )
            if not committed.cancelled:
                duration_ms = max(0, round((self.store.clock() - generation_started_at) * 1000))
                if self.record_report_metrics is not None:
                    try:
                        metrics_id = self.record_report_metrics(
                            ReportMetrics(
                                medical_condition=", ".join(catalog_condition_names(profile)),
                                min_score=min_score,
                                characters=characters,
                                ai_model=self.report_model_choice,
                                ai_effort=self.report_ai_effort,
                                duration=duration_ms,
                            )
                        )
                        logger.info(
                            "report_metrics_persisted job_id=%s metrics_id=%s",
                            operation.operation_id,
                            metrics_id,
                        )
                    except Exception as exc:
                        # Publishing has succeeded; metrics failure must not undo the PDF.
                        logger.error(
                            "report_metrics_persistence_failed job_id=%s type=%s sqlstate=%s",
                            operation.operation_id,
                            type(exc).__name__,
                            getattr(exc, "sqlstate", None),
                        )
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
            if admitted is not None:
                raise
            reply = (
                "Furnizorul AI nu este disponibil. Încercați din nou."
                if isinstance(exc, AIUnavailable)
                else "Raportul nu a putut fi generat. Încercați din nou."
            )
            return self.store.commit_operation(
                operation,
                CommitChange(
                    messages=[
                        {
                            **text_message("assistant", reply),
                            "generationSearchId": search_id,
                        }
                    ]
                ),
            )
        finally:
            if admitted is None:
                self.store.finish_operation(operation)
