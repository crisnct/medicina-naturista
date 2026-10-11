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
