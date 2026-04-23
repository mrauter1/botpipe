# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t173132-c1
- Pair: implement
- Phase ID: incident-hardening-program-package
- Phase Directory Key: incident-hardening-program-package
- Phase Title: Ship Incident Hardening Workflow
- Scope: phase-local producer artifact

## Files Changed

- `workflows/incident_to_hardening_program/__init__.py`
- `workflows/incident_to_hardening_program/workflow.toml`
- `workflows/incident_to_hardening_program/params.py`
- `workflows/incident_to_hardening_program/contracts.py`
- `workflows/incident_to_hardening_program/workflow.py`
- `workflows/incident_to_hardening_program/prompts/README.md`
- `workflows/incident_to_hardening_program/prompts/frame_producer.md`
- `workflows/incident_to_hardening_program/prompts/frame_verifier.md`
- `workflows/incident_to_hardening_program/prompts/evidence_producer.md`
- `workflows/incident_to_hardening_program/prompts/evidence_verifier.md`
- `workflows/incident_to_hardening_program/prompts/analysis_producer.md`
- `workflows/incident_to_hardening_program/prompts/analysis_verifier.md`
- `workflows/incident_to_hardening_program/prompts/program_producer.md`
- `workflows/incident_to_hardening_program/prompts/program_verifier.md`
- `workflows/incident_to_hardening_program/assets/incident_hardening_package_checklist.md`
- `docs/workflows/incident_to_hardening_program.md`
- `tests/runtime/test_incident_to_hardening_program.py`
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- `tests/test_architecture_baseline_docs.py`
- `.autoloop/tasks/recursive-framework-evolution-20260423t173132-c1/decisions.txt`

## Symbols Touched

- `IncidentToHardeningProgram`
- `Parameters`
- `IncidentFramingPayload`
- `IncidentEvidencePayload`
- `IncidentHypothesisPayload`
- `IncidentHardeningProgramPayload`
- `FRAME_INCIDENT_ROUTE_CONTRACTS`
- `ASSEMBLE_EVIDENCE_ROUTE_CONTRACTS`
- `RANK_CAUSE_HYPOTHESES_ROUTE_CONTRACTS`
- `PREPARE_HARDENING_PROGRAM_ROUTE_CONTRACTS`
- `test_incident_hardening_package_runs_and_emits_terminal_receipt`
- `test_recursive_memory_files_record_cycle_one_closeout_baseline`

## Checklist Mapping

- AC-1: added a discoverable `incident_to_hardening_program` package with explicit workflow topology, prompts, parameters, route contracts, and artifact contracts under `workflows/incident_to_hardening_program/`
- AC-2: added deterministic `incident_summary.json` and `incident_receipt.json` publication behavior instead of leaving the workflow at prose-only outputs
- AC-3: added `tests/runtime/test_incident_to_hardening_program.py` and validated the package together with the builder/release/runtime baseline and recursive-memory baseline

## Assumptions

- The repo-root package architecture remains authoritative; the request snapshot's `src/autoloop/...` paths are stale equivalents, not implementation targets.
- Recursive memory updates are acceptable spillover for this phase because the cycle request explicitly requires them and `tests/test_architecture_baseline_docs.py` treats those files as the shipped baseline.

## Preserved Invariants

- Runtime-injected control data remains limited to `expected_output_schema`, `available_routes`, and `route_contracts`.
- Deterministic bootstrap and publication behavior stays workflow-owned and uses the existing authoring-only lifecycle helper rather than new runtime automation.
- No changes were made to `core/engine.py`, `runtime/runner.py`, `runtime/cli.py`, or `recursive_autoloop/`.

## Intended Behavior Changes

- `autoloop` can now discover and run `incident_to_hardening_program` as a first-class workflow package.
- Cycle memory now records the incident workflow and lifecycle helper as shipped cycle-1 outcomes, and moves `security_finding_to_verified_remediation` into the deferred slot.

## Known Non-Changes

- No recursive wrapper/template cleanup; the known `require_package_autoloop_cli` and `src/autoloop/...` drift remains intentionally deferred.
- No child-workflow extraction for shared evidence or remediation subflows.
- No broader CLI, provider-adapter, or runtime-schema behavior change.

## Expected Side Effects

- `autoloop workflows list/show` now includes the incident hardening package and its aliases.
- Future cycle baselines will treat `incident_to_hardening_program` as shipped rather than deferred.

## Validation Performed

- `.venv/bin/pytest -q tests/unit/test_validation.py tests/contract/test_engine_contracts.py tests/runtime/test_workflow_builder_package.py tests/runtime/test_release_candidate_to_go_no_go.py tests/runtime/test_incident_to_hardening_program.py tests/test_architecture_baseline_docs.py`
- Observed result: `79 passed in 0.81s`

## Deduplication Or Centralization Decisions

- Reused `stdlib.lifecycle` for session opening, invocation-contract writing, and receipt writing instead of copying bootstrap/publication boilerplate into a third workflow package.
- Kept `incident_summary.json` as the machine-readable publication authority rather than trying to parse the markdown artifacts during publication.
