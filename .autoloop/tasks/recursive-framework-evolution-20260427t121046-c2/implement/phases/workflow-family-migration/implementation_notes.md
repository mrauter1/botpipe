# Implementation Notes

- Task ID: recursive-framework-evolution-20260427t121046-c2
- Pair: implement
- Phase ID: workflow-family-migration
- Phase Directory Key: workflow-family-migration
- Phase Title: Workflow Migration
- Scope: phase-local producer artifact
- Cycle mode: `consolidate`

## Pre-change audit

- Relevant workflows/helpers checked:
  - `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
  - `workflows/workflow_to_eval_suite/workflow.py`
  - `workflows/workflow_run_history_to_failure_modes/workflow.py`
  - `workflows/workflow_package_to_composable_building_blocks/workflow.py`
  - `stdlib/_selected_workflow.py` and `stdlib/optimization.py`
- Repeated pattern confirmed:
  - capture steps still did `write -> exists -> read -> validate -> selected_workflow_name extraction` even after the private selected-workflow seam already exposed the canonical name explicitly.
  - the simpler selected-workflow publish handlers still carried their own required-artifact existence loops.
  - the optimizer source-manifest helper still re-resolved selected-workflow authoring context beside the shared seam.
- Simplification chosen:
  - consume the private selected-workflow capture seam directly in the scoped workflow-family capture steps and optimizer helper path, while reusing the existing shared artifact-existence validator where it improves publish readability.
- New workflow needed: no.
- Authoring leverage target:
  - the touched workflow family should read more clearly as `capture context -> do local reasoning -> publish`, with selected-workflow identity coming from one shared seam instead of being re-read from a fresh artifact.

## Files changed

- `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
- `workflows/workflow_to_eval_suite/workflow.py`
- `workflows/workflow_run_history_to_failure_modes/workflow.py`
- `workflows/workflow_package_to_composable_building_blocks/workflow.py`
- `stdlib/optimization.py`
- `.autoloop/tasks/recursive-framework-evolution-20260427t121046-c2/decisions.txt`
- `.autoloop/tasks/recursive-framework-evolution-20260427t121046-c2/implement/phases/workflow-family-migration/implementation_notes.md`
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- `.autoloop_recursive/validation_debt_ledger.md`

## Symbols touched

- Shared seam consumption:
  - `capture_selected_workflow(...)`
  - `inspect_selected_workflow(...)`
  - `require_existing_artifact_paths(...)`
- Workflow hooks:
  - `CandidateWorkflowToAdaptedExecutionPlan.on_capture_selected_workflow_contract(...)`
  - `CandidateWorkflowToAdaptedExecutionPlan.on_publish_adapted_execution_plan(...)`
  - `WorkflowToEvalSuite.on_capture_selected_workflow_contract(...)`
  - `WorkflowToEvalSuite.on_publish_workflow_eval_suite(...)`
  - `WorkflowRunHistoryToFailureModes.on_capture_run_history_context(...)`
  - `WorkflowPackageToComposableBuildingBlocks.on_capture_decomposition_context(...)`
- Optimizer helper path:
  - `capture_optimization_frame_context(...)`
  - `write_selected_workflow_source_manifest(...)`

## Checklist mapping

- `phase_plan.yaml` `workflow-family-migration` AC-1:
  - satisfied by removing the selected-workflow-name re-read tails from the scoped capture steps in adaptation, eval-suite, run-history, and decomposition/optimizer-adjacent paths.
- `phase_plan.yaml` `workflow-family-migration` AC-2:
  - satisfied by keeping publish-time checks focused on domain alignment while moving the simpler required-artifact existence loops onto the shared validator in the adapted and eval-suite publish handlers.

## Preserved invariants

- No CLI, runtime/provider, `workflow.toml`, or `ctx.invoke_workflow(...)` behavior changed.
- No artifact filename, top-level JSON schema, prompt path, route name, or receipt name changed.
- The selected-workflow helper seam remains authoring-only and additive.
- Workflow-local publish handlers still own domain-specific policy and receipt shaping.

## Intended behavior changes

- None at the public contract level.
- Internal workflow capture ownership changed: the canonical `selected_workflow_name` now comes from the private selected-workflow seam instead of being re-read from newly written artifacts in the scoped family.

## Known non-changes

- No new workflow package was added.
- No prompt contract or publication-policy rewrite was attempted.
- `stdlib/evaluation.py` still keeps its existing helper-local snapshot validation path in this phase.
- `workflow_run_traces_to_optimization_candidates` workflow topology and package artifacts remain unchanged; only the shared optimizer helper path was tightened.

## Expected side effects

- The scoped capture handlers are shorter and easier to read because they no longer mix name recovery with artifact creation.
- Optimizer-family source-manifest capture now shares the same selected-workflow resolution path as the rest of the selected-workflow family.
- The remaining selected-workflow publication checks are clearer to evaluate because generic file-existence validation moved to a shared helper where appropriate.

## Deduplication / centralization decisions

- Kept the convergence in the existing private seam `stdlib/_selected_workflow.py` instead of adding another public stdlib helper.
- Reused `require_existing_artifact_paths(...)` for the simpler publish handlers rather than keeping per-workflow existence loops.
- Left decomposition and run-history publish policy local because the remaining checks are boundary- and evidence-specific rather than generic selected-workflow identity mechanics.

## Validation performed

- `.venv/bin/python -m py_compile workflows/candidate_workflow_to_adapted_execution_plan/workflow.py workflows/workflow_to_eval_suite/workflow.py workflows/workflow_run_history_to_failure_modes/workflow.py workflows/workflow_package_to_composable_building_blocks/workflow.py stdlib/optimization.py`
- `.venv/bin/pytest -q tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
- `.venv/bin/pytest -q tests/runtime/test_workflow_to_eval_suite.py`
- `.venv/bin/pytest -q tests/runtime/test_workflow_run_history_to_failure_modes.py`
- `.venv/bin/pytest -q tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- `.venv/bin/pytest -q tests/runtime/test_workflow_run_traces_to_optimization_candidates.py`
- `.venv/bin/pytest -q tests/unit/test_optimization_helpers.py`
- `.venv/bin/pytest -q tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
- `.venv/bin/pytest -q tests/test_architecture_baseline_docs.py`

## Assumptions

- Phase scope allows the optimizer helper touch because the acceptance criteria explicitly include optimizer-family selected-workflow capture/publish integration where the same seam applies.
- The standing recursive memory files should record this phase as a consolidation closeout note rather than as a new-workflow candidate promotion.
