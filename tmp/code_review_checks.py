"""Review probes using synthetic data, with no database or external API calls."""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


os.environ['LOG_LEVEL'] = 'ERROR'
os.environ['LOG_AI_RESPONSE_TEXT'] = 'false'
os.environ['LOG_FRAGMENT_TEXT'] = 'false'
os.environ['CONDITION_AI_BACKENDS'] = ''
os.environ['SESSION_TEMP_DIR'] = tempfile.mkdtemp(prefix='code-review-')

from backend.ai import retrieval, condition_ai
from backend.ai.client import ResponsesClient
from backend.ai.providers import provider_config
from backend.config import settings
from backend.core.models import HealthProfile, PendingSearch, StoredReport
from backend.core.sessions import SessionStore

# Import the app without its production database initializer.
with patch.object(retrieval, 'Retriever', return_value=SimpleNamespace(document_count=0, category_tree=None)):
    from backend.web import main

logging.disable(logging.CRITICAL)

def probes():
    out = {}
    from starlette.requests import Request
    with tempfile.TemporaryDirectory() as temp:
        local_store = SessionStore(Path(temp), 60, 120)
        with patch.object(main, 'store', local_store), patch.object(main.ai, 'is_configured', return_value=True):
            out['api_session_registered'] = any(getattr(route, 'path', '') == '/api/session' for route in main.app.routes)
            out['prefixed_api_session_registered'] = any(getattr(route, 'path', '') == '/medicina/api/session' for route in main.app.routes)
            for number in range(30):
                request = Request({'type': 'http', 'headers': [(b'cookie', b'naturist_sid=' + b'a' * 32), (b'x-tab-id', f'synthetic-tab-{number}'.encode())]})
                main.get_session(request)
            out['get_created_sessions'] = local_store.count()
            out['health_with_stubbed_key_only'] = main.healthz()

    from uvicorn.protocols.utils import get_path_with_query_string
    out['owner_access_log_path'] = get_path_with_query_string({'path': '/owner', 'query_string': b'key=synthetic-review-key'})

    retriever = object.__new__(retrieval.Retriever)
    retriever._known_category_ids = frozenset({'allowed'})
    profile = HealthProfile(health_problem='gripa')
    session = SimpleNamespace(profile=profile, selected_categories={'removed-category'})
    with patch.object(retrieval, 'rank', return_value=[]) as rank:
        retriever.collect(session, 100)
        out['unknown_categories_filter'] = rank.call_args.kwargs['category_ids']

    ai = ResponsesClient(provider_config(settings), settings)
    with patch.object(ai, 'complete_json', return_value={'uz_intern': [{'text': 'Synthetic claim', 'evidence_ids': ['MISSING']}]}):
        out['unknown_evidence_ids'] = ai.generate({'health_problem': 'synthetic'}, {'C1': {'source': 'synthetic.md:1', 'text': 'synthetic'}})['uz_intern'][0]['evidence_ids']
    with patch.object(ai, 'complete_json', return_value={'unexpected_schema': True}):
        out['invalid_report_schema_items'] = sum(len(items) for items in ai.generate({'health_problem': 'synthetic'}, {'C1': {'source': 'synthetic.md:1', 'text': 'synthetic'}}).values())
    ai.close()

    with tempfile.TemporaryDirectory() as temp:
        local_store = SessionStore(Path(temp), 60, 120)
        session = local_store.get('synthetic-cookie', 'synthetic-tab', create=True)
        session.add_search('search', PendingSearch({'health_problem': 'synthetic'}, {'C1': {'source': 'synthetic.md:1', 'text': 'synthetic'}}))
        entered, resume = threading.Event(), threading.Event()
        def delayed_generate(*args):
            entered.set()
            if not resume.wait(5):
                raise RuntimeError('probe timeout')
            return {'uz_intern': []}
        with patch.object(main.ai, 'generate', side_effect=delayed_generate), patch.object(main, 'create_pdf', return_value=b'synthetic-pdf'):
            worker = threading.Thread(target=main._generate_report, args=(session, 'search'))
            worker.start()
            if not entered.wait(5):
                raise RuntimeError('probe did not start')
            local_store.delete('synthetic-cookie', 'synthetic-tab')
            out['searches_after_delete'] = len(session.searches)
            resume.set()
            worker.join(5)
            out['report_added_after_delete'] = bool(session.report_bytes)
            out['deleted_session_registered'] = local_store.count()

    condition_ai.clear_cache()
    with patch.object(condition_ai, '_ask', return_value=({'index': 1, 'name': 'Synthetic', 'terms': ['Synthetic']},)):
        condition_ai._identify(('local',), ('synthetic sensitive message',))
        out['condition_cache_after_session_delete'] = condition_ai._identify.cache_info().currsize
    condition_ai.clear_cache()
    print(json.dumps(out, indent=2))

def tests():
    logging.disable(logging.NOTSET)
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    excluded = {'test_build_hybrid_index.py', 'test_categories.py', 'test_search.py', 'test_web.py'}
    for path in sorted(Path('src/tests/unit').rglob('test_*.py')):
        if path.name not in excluded:
            suite.addTests(loader.loadTestsFromName('.'.join(path.relative_to('src').with_suffix('').parts)))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    print(json.dumps({'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped), 'excluded_modules': sorted(excluded)}))
    return result.wasSuccessful()

if __name__ == '__main__':
    probes()
    if not tests():
        raise SystemExit(1)
