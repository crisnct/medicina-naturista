from pathlib import Path
import re
root=Path('.')
main_path=root/'src/backend/web/main.py'
main=main_path.read_text(encoding='utf-8')
handlers=root/'src/backend/web/handlers.py'
render=handlers.read_text(encoding='utf-8')
# Public rendering API; old handler imports stay available for existing consumers.
names=re.findall(r'^def (_\w+)\(',render,re.M)
for name in sorted(names,key=len,reverse=True):
    render=re.sub(r'\b'+name+r'\b',name[1:],render)
(root/'src/backend/reporting/chat.py').write_text(render,encoding='utf-8')
handlers.write_text('"""Compatibility exports for the public report/chat rendering API."""\n\nfrom backend.reporting.chat import (\n'+''.join(f'    {n[1:]} as {n},\n' for n in names)+'    GENERATE_LABEL as GENERATE_LABEL,\n)\n',encoding='utf-8')
# Capture constants and domain notices before deleting them from HTTP transport.
constants=main[main.index('NO_FRAGMENT_ABOVE_MIN_SCORE ='):main.index('router = APIRouter()')]
helpers=main[main.index('# Documents the given category'):main.index('# Serialize one category node')]
helpers=helpers.replace('_document_count_for_categories','document_count_for_categories').replace('_needs_condition_ai','needs_condition_ai').replace('_report_started_message','report_started_message').replace('_condition_identified_message','condition_identified_message').replace('_text','text_message')
# Domain orchestration comes from the same behavior already covered by HTTP tests.
message=main[main.index('def post_message('):main.index('@router.post("/api/condition")')]
message=message[message.index('    message = payload.message.strip()'):]
message=message.replace('payload.message','message').replace('signals = payload.signals.to_signals()','signals = signals').replace('categories = set(payload.categories)','categories = set(categories)')
message=message.replace('raise HTTPException(\n            422,','raise ApplicationError(\n            "MESSAGE_TOO_LONG",').replace('caractere.",\n        )','caractere.",\n            422,\n        )')
condition=main[main.index('def post_condition('):main.index('@router.post("/api/search")')]
condition=condition[condition.index('    try:'):].replace('_current(request)','session').replace('_revision(request)','expected_revision')
search=main[main.index('def _post_search('):main.index('def _evidence_above(')]
search=search[search.index('    try:'):].replace('_current(request)','session').replace('_revision(request)','expected_revision')
generate=main[main.index('    operation = deps.store.begin_operation(session, "generate"'):main.index('@router.post("/api/searches/{search_id}/generate"')]
filter_func=main[main.index('def _evidence_above('):main.index('def _generate_report(')]
for old,new in [('_text','text_message'),('_needs_condition_ai','needs_condition_ai'),('_condition_identified_message','condition_identified_message'),('_document_count_for_categories','document_count_for_categories'),('_report_started_message','report_started_message'),('_fragments_message','fragments_message'),('_generate_message','generate_message'),('_report_filename','report_filename'),('_download_message','download_message'),('_recommendation_text','recommendation_text'),('_evidence_above','evidence_above')]:
    message=re.sub(r'\b'+old+r'\b',new,message)
    condition=re.sub(r'\b'+old+r'\b',new,condition)
    search=re.sub(r'\b'+old+r'\b',new,search)
    generate=re.sub(r'\b'+old+r'\b',new,generate)
    filter_func=re.sub(r'\b'+old+r'\b',new,filter_func)
header='''"""Conversation orchestration, independent of FastAPI and frontend modules."""
from __future__ import annotations

import copy
import logging
import re
import secrets
from dataclasses import dataclass, replace
from typing import Any

from backend.ai.client import AIUnavailable
from backend.ai.condition_ai import resolved_for
from backend.ai.conditions import ResolvedQuery, resolve_query
from backend.ai.categories import category_selection
from backend.ai.index_state import index_reader
from backend.ai.retrieval import Retriever
from backend.ai.report_validation import ValidatedReport, validate_report
from backend.ai.search import ALL_SIGNALS, SearchSignals
from backend.config import Settings
from backend.core.contracts import AIProtocol, RetrievalProtocol, EmailProtocol, IdentifyCondition, RenderPDF, Evidence
from backend.core.errors import ApplicationError, OperationCancelled
from backend.core.models import CommitChange, OperationResult, PendingSearch, SessionData, SessionOperation, StoredReport
from backend.core.sessions import SessionStore
from backend.core.operation_context import OperationBudget, operation_budget
from backend.integrations.gmail import EMAIL_SKIPPED
from backend.reporting.chat import text as text_message, fragments_message, generate_message, report_filename, download_message, recommendation_text

logger = logging.getLogger("naturist.conversation")
'''
class_header='''
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
        return OperationBudget(operation.deadline, self.store.clock, lambda: self.store.checkpoint(operation))

    def close(self, cookie_id: str, tab_id: str) -> dict[str, Any]:
        self.store.delete(cookie_id, tab_id)
        return {"messages": [text_message("assistant", "Sesiunea a fost închisă. Reîncărcați pagina pentru o conversație nouă.")]}
'''
def method(signature,body):
    body=body.replace('deps.', 'self.').replace('(self.identify or identify_conditions)', 'self.identify').replace('(self.email or send_report)', 'self.email').replace('(self.pdf or create_pdf)', 'self.pdf')
    return '\n    def '+signature+':\n'+''.join('    '+line if line.strip() else line for line in body.splitlines(keepends=True))
# Bind total budget around external calls; PDF/publication also have checkpoints.
message=message.replace('                status = (deps.email or send_report)(\n                    report.health_problem, report.data, report.filename, message\n                )','                with operation_budget(self.budget(operation)):\n                    status = (deps.email or send_report)(\n                        report.health_problem, report.data, report.filename, message\n                    )')
message=message.replace('            except Exception as exc:', '            except OperationCancelled:\n                raise\n            except Exception as exc:')
condition=condition.replace('        result = (deps.identify or identify_conditions)(\n            resolve_query(snapshot.profile.health_problem)\n        )','        with operation_budget(self.budget(operation)):\n            result = (deps.identify or identify_conditions)(\n                resolve_query(snapshot.profile.health_problem)\n            )')
search=search.replace('        evidence = deps.retriever.collect(snapshot, deps.ai.context_budget())','        with operation_budget(self.budget(operation)):\n            evidence = deps.retriever.collect(snapshot, deps.ai.context_budget())')
generate=generate.replace('        sections = deps.ai.generate(profile, evidence)','        with operation_budget(self.budget(operation)):\n            sections = deps.ai.generate(profile, evidence)')
generate=generate.replace('        report = (deps.pdf or create_pdf)(profile, sections, evidence, min_score)','        with operation_budget(self.budget(operation)):\n            report = (deps.pdf or create_pdf)(profile, sections, evidence, min_score)')
# No framework objects enter the service.
service=header+'\n'+constants+'\n'+helpers+filter_func+'\ndef cancelled(**extra: Any) -> dict[str, Any]:\n    return {**OperationResult(cancelled=True).as_dict(), **extra}\n'+class_header
for signature,body in [
('message(self, session: SessionData, message: str, categories: set[str], signals: SearchSignals) -> dict[str, Any]',message),
('condition(self, session: SessionData, expected_revision: int | None = None) -> dict[str, Any]',condition),
('search(self, session: SessionData, expected_revision: int | None = None) -> dict[str, Any]',search),
('generate(self, session: SessionData, search_id: str, min_score: float = 0) -> OperationResult',generate)]:
    service+=method(signature,body).replace('_cancelled(', 'cancelled(')
(root/'src/backend/core/conversation.py').write_text(service,encoding='utf-8')
# Small adapters retain request authorization and response serialization.
start=main.index('@router.post("/api/messages")'); end=main.index('@router.post("/api/searches/{search_id}/generate"')
main=main[:start]+'''def _conversation(deps: Dependencies) -> ConversationService:
    return ConversationService(deps.settings, deps.store, deps.retriever, deps.ai,
        deps.identify or identify_conditions, deps.email or send_report, deps.pdf or create_pdf)


@router.post("/api/messages")
def post_message(payload: MessageRequest, request: Request):
    return _conversation(_deps(request)).message(_current(request), payload.message, set(payload.categories), payload.signals.to_signals())


@router.post("/api/condition")
def post_condition(request: Request):
    return _conversation(_deps(request)).condition(_current(request), _revision(request))


@router.post("/api/search")
def post_search(request: Request):
    deps = _deps(request)
    if isinstance(deps.retriever, Retriever):
        with index_reader():
            return _conversation(deps).search(_current(request), _revision(request))
    return _conversation(deps).search(_current(request), _revision(request))


def _generate_report(deps: Dependencies, session: SessionData, search_id: str, min_score: float = 0) -> OperationResult:
    return _conversation(deps).generate(session, search_id, min_score)


'''+main[end:]
start=main.index('NO_FRAGMENT_ABOVE_MIN_SCORE ='); end=main.index('# Serialize one category node')
main=main[:start]+'''from backend.core.conversation import (
    ConversationService,
    WELCOME, NO_CATEGORY_SELECTED_MESSAGE, CONDITION_AI_NOTICE,
    CONDITION_NOT_IDENTIFIED_MESSAGE, CONDITION_NOT_IDENTIFIED_CONTINUES,
    CONDITION_NOT_IDENTIFIED_STOPS,
    document_count_for_categories as _document_count_for_categories,
    condition_identified_message as _condition_identified_message,
)

router = APIRouter()


'''+main[end:]
main=main.replace('from backend.web.handlers import (','from backend.reporting.chat import (')
for name in names:
    main=main.replace('    '+name+',','    '+name[1:]+' as '+name+',')
start=main.index('    cookie, tab = _identity(request)\n',main.index('def end_session')); end=main.index('@router.post("/api/session/unload"')
main=main[:start]+'''    cookie, tab = _identity(request)
    return _conversation(_deps(request)).close(cookie, tab)


'''+main[end:]
main_path.write_text(main,encoding='utf-8')
# Tests patch the domain policy, not a removed transport helper.
test=root/'src/tests/unit/web/test_web.py'
test.write_text(test.read_text(encoding='utf-8').replace('patch.object(main, "_needs_condition_ai",','patch("backend.core.conversation.needs_condition_ai",'),encoding='utf-8')
