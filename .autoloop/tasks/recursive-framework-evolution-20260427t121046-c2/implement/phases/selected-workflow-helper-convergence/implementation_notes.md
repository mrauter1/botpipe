# Implementation Notes

- Task ID: recursive-framework-evolution-20260427t121046-c2
- Pair: implement
- Phase ID: selected-workflow-helper-convergence
- Phase Directory Key: selected-workflow-helper-convergence
- Phase Title: Shared Selected-Workflow Seam
- Scope: phase-local producer artifact
- Cycle mode: `consolidate`

## Pre-change audit

- Relevant workflows/helpers checked:
  - `stdlib/adaptation.py` plus `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
  - `stdlib/diagnostics.py` plus `workflows/workflow_run_history_to_failure_modes/workflow.py`
  - `stdlib/refinement.py` / `stdlib/decomposition.py` plus their refinement/decomposition workflow consumers
- Repeated pattern confirmed: each selected-workflow writer re-resolved repo root, re-resolved the workflow reference, rebuilt the same top-level envelope fields, and then wrote one artifact-local payload.
- Simplification chosen: add one private selected-workflow capture/writer seam and rebase the helper family on it.
- New workflow needed: no.
- Authoring leverage target: let later workflow migration consume one capture object instead of repeating write-read-validate tails.

## Files changed

- `stdlib/_selected_workflow.py`
- `stdlib/adaptation.py`
- `stdlib/refinement.py`
- `stdlib/decomposition.py`
- `stdlib/diagnostics.py`
- `tests/unit/test_stdlib_and_extensions.py`
- `.autoloop/tasks/recursive-framework-evolution-20260427t121046-c2/decisions.txt`
- `.autoloop/tasks/recursive-framework-evolution-20260427t121046-c2/implement/phases/selected-workflow-helper-convergence/implementation_notes.md`

## Symbols touched

- Added:
  - `SelectedWorkflowCapture`
  - `SelectedWorkflowInspection`
  - `SelectedWorkflowArtifactWrite`
  - `capture_selected_workflow(...)`
  - `inspect_selected_workflow(...)`
  - `write_selected_workflow_artifact(...)`
- Rebased public helpers:
  - `write_selected_workflow_capability_snapshot(...)`
  - `write_validated_workflow_parameters(...)`
  - `write_selected_workflow_authoring_surface(...)`
  - `write_selected_workflow_decomposition_surface(...)`
  - `write_selected_workflow_run_history_snapshot(...)`

## Checklist mapping

- `phase_plan.yaml` `selected-workflow-helper-convergence` AC-1:
  - satisfied by `stdlib/_selected_workflow.py` owning shared repo-root resolution, `selected_workflow_name`, and envelope writing for capability, authoring-surface, decomposition-surface, and run-history artifacts.
- `phase_plan.yaml` `selected-workflow-helper-convergence` AC-2:
  - satisfied by preserving the existing artifact filenames and top-level JSON keys in the rebased public helpers.

## Preserved invariants

- No CLI, runtime/provider, or `ctx.invoke_workflow(...)` behavior changed.
- No new workflow package or `workflow.toml` semantic field was added.
- Existing selected-workflow artifact filenames and top-level schemas remained unchanged.
- Public stdlib helper entrypoints stayed stable.

## Intended behavior changes

- None at the artifact-contract level.
- Internal helper ownership changed: selected-workflow resolution and envelope writing now live in one private seam.

## Known non-changes

- No workflow-family capture-step migration in this phase.
- No docs or recursive memory ledger updates in this phase; those remain planned for later closeout phases.
- No optimization helper refactor beyond inheriting the rebased public writers indirectly.

## Expected side effects

- Later workflow migration can consume returned capture metadata to remove local write-read-validate tails with less risk.
- Unit tests that previously monkeypatched per-module resolver imports now target the shared private seam.

## Deduplication / centralization decisions

- Chosen seam: private `stdlib/_selected_workflow.py`
- Non-goal: do not widen the public authoring surface before workflow migration proves a public helper is needed.
- Kept workflow-local/domain-local payload shaping in the existing public helper modules.

## Validation performed

- `.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py`
- `.venv/bin/pytest -q tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
- `.venv/bin/pytest -q tests/runtime/test_workflow_to_eval_suite.py`
- `.venv/bin/pytest -q tests/runtime/test_workflow_run_history_to_failure_modes.py`
- `.venv/bin/pytest -q tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
- `.venv/bin/pytest -q tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- `.venv/bin/pytest -q tests/runtime/test_workflow_run_traces_to_optimization_candidates.py`
- `.venv/bin/pytest -q tests/test_architecture_baseline_docs.py`

## Assumptions

- Phase scope is limited to helper convergence, so workflow-file simplification and recursive memory/doc closeout remain deferred.
