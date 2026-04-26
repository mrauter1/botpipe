# Implementation Notes

- Task ID: recursive-framework-evolution-20260425t234529-bootstrap-bootstrap
- Pair: implement
- Phase ID: docs-and-regression-suite
- Phase Directory Key: docs-and-regression-suite
- Phase Title: Docs And Regression Sweep
- Scope: phase-local producer artifact

## Files changed

- `docs/architecture.md`
- `docs/authoring.md`
- `docs/workflows/*.md` for the 14 workflow package docs that still described the narrow contract
- `workflows/*/prompts/README.md` for the 14 scoped prompt README baselines
- workflow prompt files with stale boundary reminders:
  `release_candidate_to_go_no_go/prompts/frame_verifier.md`,
  `investigation_request_to_evidence_pack/prompts/frame_verifier.md`,
  `incident_to_hardening_program/prompts/frame_verifier.md`,
  `task_to_workflow_strategy/prompts/frame_producer.md`,
  `task_to_candidate_workflow_set/prompts/frame_producer.md`,
  `candidate_workflow_to_adapted_execution_plan/prompts/frame_producer.md`,
  `company_operation_to_recursive_improvement_cycle/prompts/frame_producer.md`,
  `workflow_to_eval_suite/prompts/frame_producer.md`,
  `workflow_run_history_to_failure_modes/prompts/frame_producer.md`,
  `workflow_portfolio_to_operating_system/prompts/frame_producer.md`,
  `workflow_and_eval_to_refined_workflow_package/prompts/frame_producer.md`,
  `workflow_package_to_composable_building_blocks/prompts/frame_producer.md`,
  `workflow_package_to_composable_building_blocks/prompts/evaluate_producer.md`,
  `workflow_idea_to_workflow_package/prompts/design_producer.md`
- baseline and regression assertions:
  `tests/test_architecture_baseline_docs.py`,
  `tests/strictness/test_no_compat.py`,
  `tests/runtime/test_release_candidate_to_go_no_go.py`,
  `tests/runtime/test_investigation_request_to_evidence_pack.py`,
  `tests/runtime/test_security_finding_to_verified_remediation.py`,
  `tests/runtime/test_incident_to_hardening_program.py`,
  `tests/runtime/test_task_to_workflow_strategy.py`,
  `tests/runtime/test_task_to_candidate_workflow_set.py`,
  `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`,
  `tests/runtime/test_workflow_to_eval_suite.py`,
  `tests/runtime/test_workflow_run_history_to_failure_modes.py`,
  `tests/runtime/test_workflow_portfolio_to_operating_system.py`,
  `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`,
  `tests/runtime/test_workflow_builder_package.py`,
  `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`,
  `tests/runtime/test_workflow_package_to_composable_building_blocks.py`

## Symbols touched

- `workflow.__all__`
- authoring-facing docs for `RenderedLLMProvider`, `ProviderTransport`, `Handoff`, `ProviderRetryPolicy`, `Event.handoff`
- prompt/readme contract language for runtime-injected provider guidance

## Checklist mapping

- AC-1 / plan item 25: updated `docs/architecture.md`, `docs/authoring.md`, workflow docs, prompt READMEs, and prompt boundary reminders to describe required inputs, writable artifacts, route-specific artifact requirements, expected payload requirements, optional retry feedback, optional route handoff, and raw-output telemetry exclusion.
- AC-2 / plan items 20-24: kept provider purity, renderer, retry, handoff, and checkpoint coverage green by updating baseline/runtime assertions to the new wording and fixing the strictness export lock for `Handoff`.
- AC-3 / plan items 22-23: ran the targeted pytest set and the full suite successfully.

## Assumptions

- Phase scope stayed documentation/regression-local; no engine/provider logic was changed.
- The public authoring surface now includes `Handoff` and `ProviderRetryPolicy`, matching the already-landed core/workflow shims.

## Preserved invariants

- No provider raw output was reintroduced into provider-facing prompts.
- Public CLI/config semantics were unchanged.
- The strict semantic provider/runtime boundary from earlier phases remained intact.

## Intended behavior changes

- Public docs and prompt guidance now describe the shared rendered Runtime Step Contract instead of the old narrow three-field contract.
- Baseline tests now lock the expanded contract wording and the raw-output telemetry boundary.

## Known non-changes

- No new provider backends, workflow-authoring features, or CLI changes were introduced.
- `runtime/providers/_common.py` and other non-phase runtime internals were left untouched.

## Expected side effects

- Workflow package docs and README tests now fail if the repo drifts back to the old `expected_output_schema` / `available_routes` / `route_contracts`-only wording.
- Strictness coverage now protects the intended `Handoff` export on the root `workflow` shim.

## Validation performed

- `.venv/bin/pytest -q tests/runtime/test_runtime_providers.py`
- `.venv/bin/pytest -q tests/runtime/test_provider_backends.py`
- `.venv/bin/pytest -q tests/contract/test_engine_contracts.py`
- `.venv/bin/pytest -q tests/unit/test_validation.py`
- `.venv/bin/pytest -q tests/unit/test_primitives_and_stores.py`
- `.venv/bin/pytest -q tests/test_architecture_baseline_docs.py`
- `.venv/bin/pytest -q tests/strictness/test_no_compat.py`
- `.venv/bin/pytest -q`

## Deduplication / centralization decisions

- Reused one shared wording family for the runtime contract and raw-output telemetry note across docs, prompt READMEs, and runtime scenario tests to avoid future phrase drift.
