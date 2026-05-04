# Implementation Notes

- Task ID: below-is-the-revised-standalone-correction-spec-91e19feb
- Pair: implement
- Phase ID: public-surface-polish
- Phase Directory Key: public-surface-polish
- Phase Title: Public Surface Cleanup
- Scope: phase-local producer artifact

## Files changed

- `autoloop/core/effects.py`
- `docs/authoring.md`
- `docs/workflows/*.md` for the active workflow package docs except the pre-existing deleted `workflow_run_traces_to_optimization_candidates.md`
- `workflows/*/prompts/README.md` including `workflows/autoloop_v1/prompts/README.md`
- `tests/test_architecture_baseline_docs.py`
- `tests/unit/test_simple_surface.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_*` prompt-README/doc assertion files touched by the route-surface wording sweep

## Symbols touched

- `autoloop.core.effects.Effects`
- `autoloop.core.effects.WorklistEffect`
- `autoloop.simple.validation_step`

## Checklist mapping

- AC-1: kept `Effects` public and documented it as an intentional hook-control API; added precedence and direct-control parity coverage.
- AC-2: kept `validation_step(...)` lowering to `python_step(...)`; added public-surface coverage for feedback writes and optional failed-route authoring.
- AC-3: updated authoring docs, workflow docs, prompt READMEs, and runtime doc assertions to remove default `blocked`/`failed` wording, remove `Artifact.managed(...)` authoring guidance, and state that `question` is the only default runtime control route.

## Assumptions

- Existing Milestone A runtime semantics from earlier phases were already correct; this phase needed documentation and coverage cleanup, not new runtime mechanics.
- The tracked deletion of `docs/workflows/workflow_run_traces_to_optimization_candidates.md` was pre-existing dirty state and was left untouched.

## Preserved invariants

- `Effects` runtime normalization and worklist-mutation execution paths remain unchanged.
- `validation_step(...)` still lowers to a `PythonStepDeclaration` and reuses the existing validation feedback rendering/runtime-event path.
- Workflow docs and prompt READMEs still keep their package-specific route/artifact payload content; only the framework-control wording was normalized.

## Intended behavior changes

- Public docs now describe `Effects` as a supported hook-control surface rather than implying only worklist-helper sugar.
- Public docs and examples now describe `question` as the only default runtime-control route and describe `blocked`/`failed` only as explicitly authored application routes.
- Public docs no longer teach `Artifact.managed(...)` or `role="managed"` as the way to represent workflow-level artifacts that are also step-produced.

## Known non-changes

- No runtime route, artifact, or worklist engine logic changed in this phase.
- No workflow package prompt bodies were rewritten beyond the shared README route-surface wording.

## Expected side effects

- Baseline documentation and workflow-package assertion tests now align with the shipped Milestone A semantics.
- Future public-surface work can build on the documented `Effects` contract instead of treating it as accidental API spillover.

## Validation performed

- `python3 -m venv .venv && .venv/bin/pip install pytest pydantic` (temporary local validation env; removed afterward)
- `.venv/bin/python -m pytest tests/unit/test_simple_surface.py tests/test_architecture_baseline_docs.py tests/contract/test_engine_contracts.py -k 'effect or validation_step or docs_cover_route_policy_lazy_runtime_and_managed_artifact_role or scoped_prompt_readmes_keep_shared_contract_sections_and_new_route_vocabulary'`
- `.venv/bin/python -m pytest tests/runtime/test_task_to_workflow_strategy.py tests/runtime/test_task_to_candidate_workflow_set.py tests/runtime/test_incident_to_hardening_program.py tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py tests/runtime/test_company_operation_to_recursive_improvement_cycle.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/runtime/test_security_finding_to_verified_remediation.py tests/runtime/test_release_candidate_to_go_no_go.py tests/runtime/test_investigation_request_to_evidence_pack.py tests/runtime/test_workflow_builder_package.py tests/runtime/test_workflow_to_eval_suite.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/runtime/test_workflow_portfolio_to_operating_system.py -k 'package_docs_capture_decision_records or prompt_readme_uses_shared_contract_sections'`

## Deduplication / centralization decisions

- Normalized the repeated route-surface wording across `docs/workflows/*.md` and workflow prompt READMEs so the framework contract is expressed consistently instead of being hand-diverged per package.
