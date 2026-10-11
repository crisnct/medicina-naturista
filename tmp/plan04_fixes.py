from pathlib import Path
import subprocess,re
for line in subprocess.check_output(['git','diff','--name-only','--','src/scripts/dictionaires'],text=True).splitlines():
    Path(line).write_bytes(subprocess.check_output(['git','show','HEAD:'+line]))
# Small lint fixes do not change extraction behavior.
for path in ['src/scripts/audit_conditions.py','src/scripts/extract_pdf_markdown.py']:
    p=Path(path); p.write_text(re.sub(r'\bl\b','line_item',p.read_text(encoding='utf-8')),encoding='utf-8')
p=Path('pyproject.toml'); s=p.read_text(); s=s.replace('"src/scripts/icd10_work"]','"src/scripts/icd10_work", "src/scripts/dictionaires"]'); s=s.replace('"pip-tools==7.6.2"]','"pip-tools==7.6.2", "pytest>=9,<10"]'); p.write_text(s)
p=Path('src/backend/ai/client.py');s=p.read_text();line='from backend.ai.report_validation import ValidatedReport, validate_report\n';s=s.replace(line,'');s=s.replace('from backend.ai.providers import',line+'from backend.ai.providers import');p.write_text(s)
p=Path('src/backend/web/main.py');s=p.read_text();start=s.index('from backend.core.conversation import');end=s.index('router = APIRouter()',start);block=s[start:end];s=s[:start]+s[end:];s=s.replace('from backend.core.errors import',block+'from backend.core.errors import');p.write_text(s)
p=Path('src/backend/reporting/chat.py');s=p.read_text().replace('from backend.core.models import SessionData','from backend.core.models import SessionData, SessionSnapshot\nfrom backend.core.contracts import ProfilePayload');s=s.replace('session: SessionData','session: SessionData | SessionSnapshot').replace('profile: dict | None','profile: ProfilePayload | None');p.write_text(s)
p=Path('src/backend/ai/condition_ai.py');s=p.read_text().replace('from backend.config import','from backend.core.contracts import IdentifiedCondition\nfrom backend.config import');s=s.replace('answers: tuple[dict[str, Any], ...]', 'answers: tuple[IdentifiedCondition, ...]');p.write_text(s)
p=Path('src/backend/core/conversation.py');s=p.read_text().replace('def evidence_above(evidence: dict[str, dict], min_score: float) -> dict[str, dict]:','def evidence_above(evidence: Evidence, min_score: float) -> Evidence:').replace('            signals = signals\n','');p.write_text(s)
p=Path('src/backend/web/handlers.py');s=p.read_text();names=re.findall(r'^def (\w+)\(',Path('src/backend/reporting/chat.py').read_text(),re.M);p.write_text('"""Compatibility exports for the public report/chat rendering API."""\nfrom backend.reporting.chat import (\n'+''.join(f'    {n} as _{n},\n' for n in names)+'    GENERATE_LABEL,\n)\n\n__all__ = '+repr(['_'+n for n in names]+['GENERATE_LABEL'])+'\n')
p=Path('src/tests/unit/web/test_web.py');s=p.read_text();s=s.replace('from backend.web import handlers, main','from backend.web import handlers, main\nfrom backend.core import conversation');
for name in ['WELCOME','NO_CATEGORY_SELECTED_MESSAGE','CONDITION_AI_NOTICE','CONDITION_NOT_IDENTIFIED_CONTINUES','CONDITION_NOT_IDENTIFIED_STOPS','CONDITION_NOT_IDENTIFIED_MESSAGE']:
    s=s.replace('main.'+name,'conversation.'+name)
for name in ['_condition_identified_message','_document_count_for_categories']:
    s=s.replace('main.'+name,'conversation.'+name[1:])
# Supply a small fixture by default. Individual dictionary tests still override it.
s=s.replace('        self.temp = tempfile.TemporaryDirectory()','        dictionary = ConditionDictionary(parse_conditions(conditions_jsonl("Gripa,flu,influenza\\nGuta,gout,podagra\\nHipertensiune,hypertension\\nMigrena,migraine\\n")))\n        fixture = patch.object(conditions_module, "load_dictionary", return_value=dictionary)\n        fixture.start()\n        self.addCleanup(fixture.stop)\n        self.temp = tempfile.TemporaryDirectory()',1)
p.write_text(s)
