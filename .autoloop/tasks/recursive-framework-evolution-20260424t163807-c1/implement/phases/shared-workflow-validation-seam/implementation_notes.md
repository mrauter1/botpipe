# Implementation Notes

- Task ID: recursive-framework-evolution-20260424t163807-c1
- Pair: implement
- Phase ID: shared-workflow-validation-seam
- Phase Directory Key: shared-workflow-validation-seam
- Phase Title: Shared Workflow Validation Seam
- Scope: phase-local producer artifact

## Pre-change audit

- Cycle mode carried from the plan: `consolidate`
- Most relevant repeated helper surfaces inspected:
- `workflows/task_to_candidate_workflow_set/workflow.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
- `workflows/workflow_to_eval_suite/workflow.py`
- Additional governance-family confirmation:
- `workflows/company_operation_to_recursive_improvement_cycle/workflow.py`
- `workflows/workflow_portfolio_to_operating_system/workflow.py`
- `workflows/workflow_run_history_to_failure_modes/workflow.py`
- Repeated idioms confirmed before edits:
- workflow-local JSON object reads
- mapping and mapping-list guards
- optional-string normalization
- deduped string-list normalization
- positive-int validation
- duplicate guards already covered by existing `require_unique_values(...)`
- New workflow not necessary; the leverage point is additive stdlib consolidation for later workflow migrations.

## Files changed

- `stdlib/validation.py`
- `stdlib/__init__.py`
- `tests/unit/test_validation.py`
- `tests/unit/test_stdlib_and_extensions.py`

## Symbols touched

- Added: `normalize_optional_string`
- Added: `normalize_unique_strings`
- Added: `read_json_object`
- Added: `require_mapping`
- Added: `require_mapping_list`
- Added: `require_positive_int`
- Reused: `require_unique_values`
- Exported from stdlib root: the six helpers above

## Checklist mapping

- Plan phase 1 / extend `stdlib/validation.py`: complete
- Plan phase 1 / export shared seam from `stdlib/__init__.py`: complete
- Plan phase 1 / focused helper coverage in `tests/unit/test_validation.py`: complete
- Plan phase 1 / focused helper coverage in `tests/unit/test_stdlib_and_extensions.py`: complete
- Workflow migrations listed in the task-wide plan: deferred to a later phase; intentionally out of this phase-local scope
- Recursive-memory file updates from the task-wide request: deferred; not part of the active phase deliverables

## Assumptions

- This phase only establishes the shared seam and freezes helper behavior; it does not migrate workflow packages yet.
- Later workflow migrations will need custom error-message preservation, so the new helpers accept optional `error_message` hooks.

## Preserved invariants

- No CLI, runtime, provider, or `workflow.toml` behavior changed.
- No root `workflow` authoring-surface expansion.
- No hidden artifacts or runtime-owned validation policy were introduced.
- `read_model_file(...)`, `validate_model_file(...)`, and `write_model_file(...)` remain stdlib-only helpers.

## Intended behavior changes

- `stdlib.validation` now exposes additive helpers for the repeated workflow-local validation idioms identified in the selected-workflow and governance family.
- Positive-int validation now has one shared helper that rejects booleans by default unless a caller opts in with `allow_bool=True`.

## Known non-changes

- No workflow file imports were migrated in this phase.
- No prompt, docs, or recursive-memory files were edited in this phase.
- Existing `require_non_empty_string(...)`, `require_string_list(...)`, and `require_unique_values(...)` behavior was preserved.

## Expected side effects

- Later workflow migrations can replace copied helper tails with stdlib imports while preserving current artifact-level error wording.
- Unit tests now freeze the new helper seam closely enough to reduce silent contract drift during those migrations.

## Validation performed

- `python3 -m py_compile stdlib/validation.py stdlib/__init__.py tests/unit/test_validation.py tests/unit/test_stdlib_and_extensions.py`
- `python3 -m pytest ...`: could not run because `pytest` is not installed in the current environment
- Import-level smoke via `python3` against the package namespace: blocked because the current environment also lacks `pydantic`

## Deduplication / centralization decisions

- Centralized generic JSON-object reads under `read_json_object(...)` instead of repeating `json.loads(path.read_text(...))` in future workflow files.
- Centralized shared mapping/list/int/string normalization in stdlib; domain-specific publication assertions remain workflow-local by design.
