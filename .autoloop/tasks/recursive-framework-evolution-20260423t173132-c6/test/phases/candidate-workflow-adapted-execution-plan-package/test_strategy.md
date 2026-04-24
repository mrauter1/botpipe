# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c6
- Pair: test
- Phase ID: candidate-workflow-adapted-execution-plan-package
- Phase Directory Key: candidate-workflow-adapted-execution-plan-package
- Phase Title: Adapted Execution Plan Package
- Scope: phase-local producer artifact

## Behaviors covered

- Discovery and compilation coverage for `candidate_workflow_to_adapted_execution_plan`, including explicit route-contract wiring and the package-step required payload fields in the compiled `expected_output_schema`.
- Happy-path runtime publication of the adapted plan, summary, next-action artifact, validated workflow parameters, and deterministic receipt.
- Preserved invariant that the building block stops at publication and does not auto-run the selected workflow.

## Edge cases and failure paths

- Parameter coercion rejects blank `selected_workflow` and normalizes repeatable task-context inputs.
- Package-step non-ready callback path (`needs_rework`) updates state cleanly with explicit package payload fields.
- Compiled package-step validator rejects missing `selected_workflow_parameters_supported`, `proposed_parameter_keys`, or `ready_for_execution` before callback execution.
- Publish-time validation rejects invalid selected-workflow references, invalid proposed parameter mappings, missing authoritative-artifact declarations, and summary drift from validated parameter keys.

## Stabilization notes

- Tests stay deterministic by using `ScriptedLLMProvider`, temporary repo copies under `tmp_path`, and direct compiled-validator checks for the package-step failure path instead of a second large scripted provider run.

## Known gaps

- No dedicated full engine run for an invalid package verifier payload; the validator-level failure test covers the same runtime-owned contract with less fixture duplication and lower flake risk.
