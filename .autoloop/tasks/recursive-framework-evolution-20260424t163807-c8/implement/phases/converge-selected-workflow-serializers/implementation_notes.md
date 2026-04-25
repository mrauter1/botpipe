# Implementation Notes

- Task ID: recursive-framework-evolution-20260424t163807-c8
- Pair: implement
- Phase ID: converge-selected-workflow-serializers
- Phase Directory Key: converge-selected-workflow-serializers
- Phase Title: Converge Selected-Workflow Serializers
- Scope: phase-local producer artifact

## Audit

- Cycle mode: `consolidate`
- Three most relevant existing helpers/workflows checked:
  - `stdlib/adaptation.py` + `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
  - `stdlib/refinement.py` + `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`
  - `stdlib/decomposition.py` + `workflows/workflow_package_to_composable_building_blocks/workflow.py`
- Repeated patterns confirmed:
  - selected-workflow payload shaping duplicated across `stdlib/adaptation.py`, `stdlib/refinement.py`, and `stdlib/decomposition.py`
  - repeated selected-workflow identity alignment checks in adaptation, eval-suite, run-history, refinement, and decomposition workflows
- Simplification opportunity chosen: centralize selected-workflow payload builders in `core/workflow_capabilities.py` and move generic selected-workflow snapshot validation into `stdlib/validation.py`
- New workflow necessary: no

## Files Changed

- `core/workflow_capabilities.py`
- `stdlib/adaptation.py`
- `stdlib/refinement.py`
- `stdlib/decomposition.py`
- `stdlib/validation.py`
- `stdlib/__init__.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
- `workflows/workflow_to_eval_suite/workflow.py`
- `workflows/workflow_run_history_to_failure_modes/workflow.py`
- `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`
- `workflows/workflow_package_to_composable_building_blocks/workflow.py`
- `tests/unit/test_stdlib_and_extensions.py`
- `docs/authoring.md`
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- `.autoloop_recursive/validation_debt_ledger.md`
- `.autoloop/tasks/recursive-framework-evolution-20260424t163807-c8/decisions.txt`

## Symbols Touched

- `selected_workflow_capability_payload(...)`
- `selected_workflow_authoring_surface_payload(...)`
- `selected_workflow_decomposition_surface_payload(...)`
- `validate_selected_workflow_capability_snapshot(...)`
- `validate_selected_workflow_authoring_surface_snapshot(...)`
- `validate_selected_workflow_decomposition_surface_snapshot(...)`
- `validate_selected_workflow_name_alignment(...)`
- `write_selected_workflow_capability_snapshot(...)`
- `write_selected_workflow_authoring_surface(...)`
- `write_selected_workflow_decomposition_surface(...)`
- workflow-local selected-workflow validation paths in adaptation, eval-suite, run-history, refinement, and decomposition publication/capture steps

## Checklist Mapping

- Plan: centralize selected-workflow payload building in `core/workflow_capabilities.py`
  - Completed via authoritative capability, authoring-surface, and decomposition-surface payload builders plus shared path/repo-relative helpers.
- Plan: slim stdlib selected-workflow writers into thin artifact emitters
  - Completed in `stdlib/adaptation.py`, `stdlib/refinement.py`, and `stdlib/decomposition.py`.
- Plan: add shared selected-workflow validators and replace repeated workflow-local checks
  - Completed in `stdlib/validation.py` plus the five targeted workflows.
- Plan: update docs, proof, and recursive memory
  - Completed with `docs/authoring.md`, `tests/unit/test_stdlib_and_extensions.py`, targeted runtime/doc proof, and all standing recursive-memory files.

## Preserved Invariants

- No new workflow package added.
- No runtime-owned routing, execution, provider, or CLI behavior changed.
- `ctx.invoke_workflow(...)` compatibility preserved.
- Artifact filenames preserved:
  - `selected_workflow_capability.json`
  - `selected_workflow_authoring_surface.json`
  - `selected_workflow_decomposition_surface.json`
- Top-level JSON contracts for those artifacts preserved.
- Workflow-specific publication semantics remain local:
  - eval-suite case coverage rules
  - run-history evidence and severity rules
  - refinement overlay/evaluation rules
  - decomposition building-block policy

## Intended Behavior Changes

- None at the user-facing artifact contract layer.
- Internal behavior now routes selected-workflow payload construction through one authoritative core builder surface and routes generic selected-workflow identity validation through one stdlib validation seam.

## Known Non-Changes

- Did not merge capability, authoring-surface, and decomposition-surface artifacts into one file.
- Did not widen `workflow.toml`.
- Did not move domain-specific publication assertions into stdlib.
- Did not change prompt contracts, runtime/provider boundaries, or child-workflow composition behavior.

## Deduplication / Centralization

- Removed duplicated runtime-test inference and editable path assembly from the selected-workflow stdlib helper family.
- Replaced repeated selected-workflow capability snapshot identity checks in adaptation and eval-suite workflows.
- Replaced repeated selected-workflow cross-artifact identity checks in run-history, refinement, and decomposition workflows with shared validators.

## Validation Performed

- Syntax: `./.venv/bin/python -m py_compile core/workflow_capabilities.py stdlib/adaptation.py stdlib/refinement.py stdlib/decomposition.py stdlib/validation.py stdlib/__init__.py workflows/candidate_workflow_to_adapted_execution_plan/workflow.py workflows/workflow_to_eval_suite/workflow.py workflows/workflow_run_history_to_failure_modes/workflow.py workflows/workflow_and_eval_to_refined_workflow_package/workflow.py workflows/workflow_package_to_composable_building_blocks/workflow.py`
- Proof: `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py tests/runtime/test_workflow_to_eval_suite.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/test_architecture_baseline_docs.py`
- Result: `218 passed`

## Expected Side Effects

- Future selected-workflow helper additions can reuse one core payload builder instead of cloning path and route serialization.
- Future workflow-local selected-workflow validation can call shared validators without widening runtime behavior.

## Deferred Debt

- Keep local for now:
  - eval-suite case-count and case-kind publication rules
  - run-history evidence-run and severity-specific diagnostics rules
  - refinement baseline/candidate overlay and evaluation-summary alignment
  - decomposition building-block index and allowed-path policy
