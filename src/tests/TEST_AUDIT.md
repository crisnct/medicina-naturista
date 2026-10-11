# Test cleanup audit — 2026-10-10

Reviewed the test inventory and checked removal candidates against their retained
coverage. Removed 17 test definitions, including three files and four test classes.
The other tests protect distinct behavior, failure paths, or input boundaries.

| Python inventory | Before cleanup | After cleanup |
| --- | ---: | ---: |
| Test files | 28 | 25 |
| Classes declaring tests | 82 | 78 |
| Test definitions, before parametrization | 516 | 499 |

Counts use the working-tree snapshot immediately before the edits. Pytest expands
the remaining definitions into 515 cases. The frontend retains all 45 tests in
10 files; its browser, persistence, and UI contracts are distinct from backend
coverage.

## Removal decisions

Paths below are relative to `src/tests`.

| Removed tests | Count | Reason and retained coverage |
| --- | ---: | --- |
| `integration/test_application.py` | 1 | Only checked that two routes appear in OpenAPI. `unit/web/test_web.py` exercises health responses and actual report generation/downloads. |
| `unit/core/test_models.py` | 1 | Only checked the default profile's type. Session lifecycle and web intake tests use the real profile and verify its state and behavior. |
| `unit/ai/test_resources.py` | 1 | File existence and parent-directory assertions duplicated actual resource loading. `query_terms` reads its resource at import; report generation tests read and verify the system prompt. These source-tree assertions did not verify an installed wheel. |
| `DocumentNameTests` in `unit/ai/test_fragmenter.py` | 1 | Inspected parameter names instead of behavior. Retained heading, condition, fragmentation, and source-line tests. |
| Three derived-weight tests in `unit/ai/test_search.py` | 3 | Disabled weights, priority relationships, and equal lexical/semantic weights already follow from the retained exact expected weights for all seven combinations. Behavioral ranking tests remain. |
| `BudgetTests.test_everything_is_returned_when_the_budget_is_large` | 1 | Moved its four-result assertion into the existing budget-boundary test, which already performs the same unrestricted search. |
| Dictionary parsing and duplicate-condition checks in `unit/ai/test_conditions.py` | 2 | Parsing and minimum synonym counts are covered by complete-line validation. Global term ownership also includes canonical names and rejects duplicate conditions. Moved the minimum dictionary-size assertion into that ownership test. |
| DeepSeek budget and default xAI streaming checks in `unit/ai/test_client_providers.py` | 2 | Retained per-provider budget tests and exact xAI payload validation. Added the single-request assertion to the payload test. |
| `CleanDocumentsTests.test_leaves_an_already_compact_file_untouched` | 1 | The retained second-run idempotence test checks zero changes, identical contents, and unchanged modification time. |
| Evidence ordering and Responses API request tests in `unit/web/test_web.py` | 2 | Kept evidence ordering with explicit source/text preservation. Provider payload tests verify the complete request and single-call count. |
| PDF source-string and absent-attachment checks in `unit/web/test_web.py` | 2 | Removed assertions against implementation spelling/layout constants and an obsolete attribute. Moved numbered-heading verification to the generated-PDF test; session isolation and cleanup tests remain. |

Retained the ornament existence test because PDF generation permits a missing
ornament. Retained security, owner revocation, concurrency, index rollback,
medical dictionary/catalogue, dosage preservation, and report validation tests.
Infrastructure errors were investigated separately and were not reasons to
delete tests. Production code was not changed by this cleanup.

## Validation

The Python Docker SDK could not access Docker Desktop's named pipe. Tests used
the fixture's existing `TEST_POSTGRES_URL` option with a separate disposable
pgvector container started through the Docker CLI. No application database was
used.

```powershell
$env:TEST_POSTGRES_URL = '<disposable test database URL>'
.venv/Scripts/python.exe -m pytest src/tests -q -rs --tb=short --disable-warnings
```

Final results:

- Backend: **505 passed, 10 skipped**, including 6,426 passing subtests.
  The skips are nine PDF extraction tests requiring optional PDF dependencies
  and one explicitly opt-in local-corpus test.
- Frontend: **45 passed** across all 10 files.
- Ruff undefined-name/unused-import checks passed for all edited Python modules.
- `git diff --check -- src/tests` passed.

The disposable database container was removed after validation.
