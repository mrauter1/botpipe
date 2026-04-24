# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t173132-c8
- Pair: implement
- Phase ID: workflow-and-eval-to-refined-workflow-package
- Phase Directory Key: workflow-and-eval-to-refined-workflow-package
- Phase Title: Workflow And Eval To Refined Workflow Package
- Scope: phase-local producer artifact

## Files Changed

- `workflows/workflow_and_eval_to_refined_workflow_package/__init__.py`
- `workflows/workflow_and_eval_to_refined_workflow_package/workflow.toml`
- `workflows/workflow_and_eval_to_refined_workflow_package/params.py`
- `workflows/workflow_and_eval_to_refined_workflow_package/contracts.py`
- `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`
- `workflows/workflow_and_eval_to_refined_workflow_package/prompts/README.md`
- `workflows/workflow_and_eval_to_refined_workflow_package/prompts/frame_producer.md`
- `workflows/workflow_and_eval_to_refined_workflow_package/prompts/frame_verifier.md`
- `workflows/workflow_and_eval_to_refined_workflow_package/prompts/design_producer.md`
- `workflows/workflow_and_eval_to_refined_workflow_package/prompts/design_verifier.md`
- `workflows/workflow_and_eval_to_refined_workflow_package/prompts/implement_producer.md`
- `workflows/workflow_and_eval_to_refined_workflow_package/prompts/implement_verifier.md`
- `workflows/workflow_and_eval_to_refined_workflow_package/prompts/evaluate_producer.md`
- `workflows/workflow_and_eval_to_refined_workflow_package/prompts/evaluate_verifier.md`
- `workflows/workflow_and_eval_to_refined_workflow_package/assets/refinement_package_checklist.md`
- `docs/workflows/workflow_and_eval_to_refined_workflow_package.md`
- `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
- `tests/test_architecture_baseline_docs.py`
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`

## Symbols Touched

- `WorkflowAndEvalToRefinedWorkflowPackage`
- `Parameters`
- `RefinementRequestFramingPayload`
- `WorkflowRefinementPlanPayload`
- `WorkflowRefinementBuildPayload`
- `WorkflowRefinementEvaluationPayload`
- `_write_baseline_workflow_manifest(...)`
- `_write_candidate_workflow_manifest(...)`
- `_validate_candidate_overlay(...)`
- `_resolve_overlay_source_root(...)`
- `_is_runnable_repo_root(...)`
- `_preserved_workflow_modules()`

## Acceptance Criteria Mapping

- AC-1: satisfied by the new workflow package discovery/compile proof and explicit typed control-contract assertions in `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
- AC-2: satisfied by the scripted success-path runtime proof that publishes baseline snapshot, candidate workflow surface, candidate manifest, refinement receipt, and verification artifacts without mutating the authoritative selected workflow package
- AC-3: satisfied by publish-step validation plus targeted rejection tests for missing evidence, selected-workflow/authoring-surface mismatch, manifest drift, selected-workflow state mismatch, and candidate files outside the selected boundary
- AC-4: satisfied by the prompt README plus the eight step prompt templates that make reads, writes, routes, evidence, and forbidden actions explicit

## Assumptions

- The current repo-root package layout (`core/`, `runtime/`, `stdlib/`, repo-root `workflows/`) remains authoritative for cycle 8; stale `src/autoloop/...` request paths were not revived
- The paired `stdlib/refinement.py` seam from `refinement-surface-seam` was already approved and available for consumption in this phase
- Candidate publication must stop before promotion and must not mutate the authoritative selected workflow package

## Preserved Invariants

- Runtime/provider control boundary stays limited to `expected_output_schema`, `available_routes`, and `route_contracts`
- The authoritative selected workflow package remains unchanged during candidate publication
- Candidate edits stay scoped to the selected workflow boundary plus its linked doc/runtime-test surface
- No public CLI, runtime contract, provider contract, or `workflow.toml` schema expansion was introduced

## Intended Behavior Changes

- Adds `workflow_and_eval_to_refined_workflow_package` as a reusable closed-loop refinement building block
- Adds deterministic publish-time candidate validation, including baseline/candidate manifest checks and isolated overlay compile/test proof
- Records cycle 8 recursive-memory baseline so future cycles treat refinement publication as shipped rather than deferred

## Known Non-Changes

- No auto-running of evaluation suites or portfolio-routing workflows
- No promotion of the candidate package into the authoritative selected workflow package
- No changes to `recursive_autoloop/`, public CLI flags, session schema, or provider backend behavior

## Expected Side Effects

- Refinement workflows now emit baseline and candidate workflow-surface artifacts plus a publication receipt under the workflow-local task directory
- Publish-time validation may copy a runnable repo root into a temp directory when the active refinement root is only a stripped phase-local workspace
- The workflow package now re-exports `_write_candidate_workflow_manifest(...)` for runtime-test inspection only

## Validation Performed

- `./.venv/bin/pytest -q tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/test_architecture_baseline_docs.py`
- Result: `47 passed`

## Deduplication / Centralization Decisions

- Reused the existing `write_selected_workflow_capability_snapshot(...)` and `write_selected_workflow_authoring_surface(...)` seams instead of expanding one helper to own both compiled-contract and editable-surface concerns
- Kept candidate-manifest derivation deterministic in workflow code rather than trusting a provider-authored manifest
- Kept overlay validation inside the workflow package and preserved `workflows.*` module cache around temp-root imports instead of widening runtime-owned refinement behavior
