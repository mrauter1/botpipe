# Test Strategy

- Task ID: recursive-framework-evolution-20260424t163807-c10
- Pair: test
- Phase ID: typed-publication-artifact-contracts
- Phase Directory Key: typed-publication-artifact-contracts
- Phase Title: Typed Publication Artifact Contracts
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- Behavior: workflow-local typed summary contracts exist for the scoped workflow family and match the on-disk JSON shape, including the split from verifier-only `summary` fields.
  - Coverage: `tests/unit/test_stdlib_and_extensions.py::test_workflow_local_json_artifact_specs_cover_summary_and_manifest_contracts`
  - Coverage: `tests/unit/test_stdlib_and_extensions.py::test_split_summary_artifact_specs_match_on_disk_json_shapes`
- Behavior: the direct-fit validated eval manifest stays typed and readable through the shared model-file seam.
  - Coverage: `tests/unit/test_stdlib_and_extensions.py::test_workflow_local_json_artifact_specs_cover_summary_and_manifest_contracts`
- Behavior: candidate publish flow still succeeds and preserves existing artifact names/keys while consuming the typed summary contract.
  - Coverage: `tests/runtime/test_task_to_candidate_workflow_set.py::test_task_to_candidate_workflow_set_package_runs_and_publishes_terminal_candidate_artifacts`
- Behavior: candidate publish flow still rejects invalid summary policy states after the typed read.
  - Coverage: `tests/runtime/test_task_to_candidate_workflow_set.py::test_task_to_candidate_workflow_set_publish_rejects_summary_without_builder_baseline`
  - Coverage: `tests/runtime/test_task_to_candidate_workflow_set.py::test_task_to_candidate_workflow_set_publish_rejects_compose_posture_with_only_one_recommended_workflow`
  - Coverage: `tests/runtime/test_task_to_candidate_workflow_set.py::test_task_to_candidate_workflow_set_publish_rejects_summary_without_strategy_ready_signal`
- Behavior: strategy publish flow still succeeds for both direct-fit and adapt handoffs while consuming typed local and child summary contracts.
  - Coverage: `tests/runtime/test_task_to_workflow_strategy.py::test_task_to_workflow_strategy_package_runs_and_publishes_terminal_strategy_artifacts`
  - Coverage: `tests/runtime/test_task_to_workflow_strategy.py::test_task_to_workflow_strategy_runs_and_publishes_concrete_adapt_handoff_without_widening_summary_fields`
- Behavior: strategy publish flow still rejects invalid builder/composition/adapt-handoff states after the typed read.
  - Coverage: `tests/runtime/test_task_to_workflow_strategy.py::test_task_to_workflow_strategy_publish_strategy_rejects_summary_without_builder_baseline`
  - Coverage: `tests/runtime/test_task_to_workflow_strategy.py::test_task_to_workflow_strategy_publish_strategy_rejects_compose_summary_with_only_one_workflow`
  - Coverage: `tests/runtime/test_task_to_workflow_strategy.py::test_task_to_workflow_strategy_publish_strategy_rejects_non_concrete_adapt_handoff`
- Behavior: adaptation publish flow still succeeds and rejects summary/validated-parameter drift after typed artifact adoption.
  - Coverage: `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py::test_candidate_workflow_to_adapted_execution_plan_package_runs_and_publishes_terminal_adaptation_artifacts`
  - Coverage: `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py::test_candidate_workflow_to_adapted_execution_plan_publish_rejects_missing_authoritative_artifact_declaration`
  - Coverage: `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py::test_candidate_workflow_to_adapted_execution_plan_publish_rejects_summary_drift_from_validated_parameters`
  - Coverage: `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py::test_candidate_workflow_to_adapted_execution_plan_publish_rejects_summary_selected_workflow_mismatch`
- Behavior: eval-suite publish flow still succeeds and rejects summary/manifest drift after typed summary and manifest adoption.
  - Coverage: `tests/runtime/test_workflow_to_eval_suite.py::test_workflow_to_eval_suite_package_runs_and_publishes_terminal_eval_artifacts`
  - Coverage: `tests/runtime/test_workflow_to_eval_suite.py::test_workflow_to_eval_suite_publish_rejects_summary_selected_workflow_mismatch`
  - Coverage: `tests/runtime/test_workflow_to_eval_suite.py::test_workflow_to_eval_suite_publish_rejects_summary_drift_from_validated_manifest`

## Preserved Invariants Checked

- Artifact filenames and top-level JSON keys remain unchanged.
- No runtime-owned publication policy or CLI behavior is encoded in the tests.
- Cross-artifact workflow policy checks still fail in the workflow publish handlers, not in a new generic registry.

## Edge Cases

- Invalid typed summary payload with missing required fields returns readable validation issues.
- Split summary artifacts stay valid without verifier-only `summary` prose.
- Adapt and eval publish steps still compare typed artifact content against validated downstream artifacts and workflow state.

## Failure Paths

- Builder-baseline omission.
- Compose posture with too few recommended workflows.
- Missing strategy-ready / publication-ready flags.
- Summary drift from validated parameters or validated eval manifest.
- Non-concrete adapt handoff text.

## Flake Risk / Stabilization

- Tests stay deterministic by using temp-path fixtures, local JSON files, and the scripted fake provider.
- No timing, network, or nondeterministic ordering dependencies were added.

## Known Gaps

- Unit proof still focuses on typed artifact read/validate behavior, not on every individual Pydantic error message.
- Runtime proof remains targeted to the scoped workflow family; broader repo proof is intentionally out of phase.
