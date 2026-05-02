# Implementation Notes

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: implement
- Phase ID: enforce-repo-compatibility-gate
- Phase Directory Key: enforce-repo-compatibility-gate
- Phase Title: Enforce Repo Compatibility Gate
- Scope: phase-local producer artifact

## Files changed
- `tests/runtime/test_workflow_integration_parity.py`
- `workflows/autoloop_v1/parity.py`
- `.../decisions.txt`

## Symbols touched
- `test_copied_autoloop_v1_runs_without_repo_root_on_syspath`
- `test_autoloop_v1_runs_through_general_runtime_and_preserves_package_local_sidecars`
- `test_autoloop_v1_parity_persists_clarifications_on_resume_without_a_custom_runner`
- `autoloop_v1_session_path`
- `_AutoloopV1ParityRuntime._append_resume_clarification`

## Checklist mapping
- Repo-level regression coverage for discovered exported workflow package compatibility: kept `tests/runtime/test_workflow_integration_parity.py` on zero compile failures and aligned parity assertions to the canonical persisted session surface.
- Raw exported-workflow contract audit: validated through `tests/unit/test_simple_surface.py`.
- Package runtime validation: ran the affected exported-workflow runtime suites under `.venv`.

## Assumptions
- The canonical autoloop-v1 session persistence surface is the workflow-owned path strategy in `workflows/autoloop_v1/conventions.py`, not duplicated `*_session.json` aliases.
- Resume-time clarification persistence remains part of the autoloop-v1 parity contract and should follow the runtime’s normalized checkpoint schema.

## Preserved invariants
- Discovered exported workflow packages must compile without tolerated failures.
- Raw exported-workflow audits remain source/signature-based rather than relying only on compiled wrappers.
- Autoloop-v1 parity still records clarification text in decisions/raw logs and on the canonical plan session payload.

## Intended behavior changes
- None to the exported workflow public contract.
- Restored autoloop-v1 resume clarification logging after the runtime checkpoint field moved from `pending_question` to `pending_input.question`.

## Known non-changes
- No changes to workflow discovery behavior.
- No changes to the compiler’s raw-handler compatibility wrappers.
- No changes to exported workflow prompts, artifacts, or route contracts.

## Expected side effects
- Parity tests now assert the canonical single-file session payload shape (`plan.json`, `phases/<phase>.json`) instead of obsolete duplicate filenames.
- Resumed autoloop-v1 runs now repopulate decisions/raw-log clarification records from current checkpoint payloads.

## Deduplication / centralization decisions
- Reused `autoloop_v1_session_path(...)` in parity tests instead of hard-coding duplicate session filenames.
- Added a backward-compatible fallback in `_append_resume_clarification` rather than introducing a separate compat helper.

## Validation performed
- `./.venv/bin/pytest tests/unit/test_simple_surface.py tests/runtime/test_workflow_integration_parity.py -q`
- `./.venv/bin/pytest tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py tests/runtime/test_company_operation_to_recursive_improvement_cycle.py tests/runtime/test_incident_to_hardening_program.py tests/runtime/test_investigation_request_to_evidence_pack.py tests/runtime/test_release_candidate_to_go_no_go.py tests/runtime/test_security_finding_to_verified_remediation.py tests/runtime/test_task_to_candidate_workflow_set.py tests/runtime/test_task_to_workflow_strategy.py tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/runtime/test_workflow_builder_package.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/runtime/test_workflow_run_traces_to_optimization_candidates.py tests/runtime/test_workflow_to_eval_suite.py -q`
