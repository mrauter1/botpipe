# Implementation Notes

- Task ID: recursive-framework-evolution-20260424t163807-c2
- Pair: implement
- Phase ID: shared-validation-migration
- Phase Directory Key: shared-validation-migration
- Phase Title: Migrate Older Domain Validation
- Scope: phase-local producer artifact

## Audit

- Cycle mode: `consolidate`
- Most relevant surfaces: `stdlib/validation.py`, `workflows/investigation_request_to_evidence_pack/workflow.py`, `workflows/security_finding_to_verified_remediation/workflow.py`
- Corroborating repeats checked: `workflows/release_candidate_to_go_no_go/workflow.py`, `workflows/incident_to_hardening_program/workflow.py`, `stdlib/company.py`, `stdlib/diagnostics.py`, `stdlib/portfolio.py`
- Repeated patterns found: copied `_require_text`, `_normalize_optional_text`, `_normalize_unique_strings`, `_read_json`, local non-negative integer checks, and duplicated snapshot-filter normalization
- Simplification opportunity chosen: add the missing generic non-negative integer helper once, then delete workflow-local generic validator tails and reuse the seam in direct snapshot-helper normalization
- New workflow needed: no

## Files changed

- `stdlib/validation.py`
- `stdlib/__init__.py`
- `stdlib/company.py`
- `stdlib/diagnostics.py`
- `stdlib/portfolio.py`
- `workflows/investigation_request_to_evidence_pack/workflow.py`
- `workflows/security_finding_to_verified_remediation/workflow.py`
- `workflows/release_candidate_to_go_no_go/workflow.py`
- `workflows/incident_to_hardening_program/workflow.py`
- `tests/unit/test_validation.py`
- `tests/unit/test_stdlib_and_extensions.py`
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- `.autoloop_recursive/validation_debt_ledger.md`

## Symbols touched

- Added: `stdlib.validation.require_non_negative_int`
- Reused shared seam in: `write_company_operation_snapshot`, `write_selected_workflow_run_history_snapshot`, `write_workflow_portfolio_health_snapshot`
- Migrated workflow handlers: `on_bootstrap(...)` / `on_publish_* (...)` in the four older domain workflows

## Checklist Mapping

- Plan milestone 1: completed
  Replaced workflow-local generic validators in the four named workflows and reused the same seam in the three snapshot helper modules.
- Plan milestone 2: completed
  Added focused unit coverage for the new helper, ran the targeted unit/runtime suites, and updated recursive-memory files.

## Preserved Invariants

- Artifact names, route names, receipt filenames, and publication artifact packages are unchanged.
- `ctx.invoke_workflow(...)` composition semantics are unchanged.
- Domain-specific publication invariants stayed in workflow code.
- No CLI, runtime routing, root authoring surface, or `workflow.toml` semantics changed.

## Intended Behavior Changes

- Generic non-negative integer checks now come from `stdlib/validation.py`.
- The three snapshot helpers now reject non-string filter entries through `require_non_empty_string(..., coerce=False)` instead of local copies.
- Older domain workflows now use shared JSON/string/list/int validators for bootstrap and publish mechanics; invalid non-object JSON now fails through `read_json_object(...)` with the shared message shape.

## Known Non-Changes

- No prompt-template redesign.
- No broad `params.py` deduplication.
- No workflow additions, retirements, or composition rewrites for `release_candidate_to_go_no_go` / `incident_to_hardening_program`.

## Dedup / Centralization Decisions

- Chose one additive helper (`require_non_negative_int`) instead of leaving per-workflow copies or inventing a larger validation abstraction.
- Reused existing `require_non_empty_string`, `normalize_optional_string`, `normalize_unique_strings`, `read_json_object`, and `require_string_list` directly instead of keeping alias-heavy local helper tails.

## Validation Performed

- `./.venv/bin/python -m py_compile stdlib/validation.py stdlib/__init__.py stdlib/company.py stdlib/diagnostics.py stdlib/portfolio.py workflows/investigation_request_to_evidence_pack/workflow.py workflows/security_finding_to_verified_remediation/workflow.py workflows/release_candidate_to_go_no_go/workflow.py workflows/incident_to_hardening_program/workflow.py tests/unit/test_validation.py tests/unit/test_stdlib_and_extensions.py`
- `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/unit/test_validation.py tests/unit/test_stdlib_and_extensions.py tests/runtime/test_investigation_request_to_evidence_pack.py tests/runtime/test_security_finding_to_verified_remediation.py tests/runtime/test_release_candidate_to_go_no_go.py tests/runtime/test_incident_to_hardening_program.py` -> `123 passed`
