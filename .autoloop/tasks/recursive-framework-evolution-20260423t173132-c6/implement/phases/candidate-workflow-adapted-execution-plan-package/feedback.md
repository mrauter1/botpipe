# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260423t173132-c6
- Pair: implement
- Phase ID: candidate-workflow-adapted-execution-plan-package
- Phase Directory Key: candidate-workflow-adapted-execution-plan-package
- Phase Title: Adapted Execution Plan Package
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking`: [workflows/candidate_workflow_to_adapted_execution_plan/contracts.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/workflows/candidate_workflow_to_adapted_execution_plan/contracts.py:27) and [workflows/candidate_workflow_to_adapted_execution_plan/workflow.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/workflows/candidate_workflow_to_adapted_execution_plan/workflow.py:283) disagree about whether `proposed_parameter_keys` is required. `AdaptedExecutionPlanPayload` gives the field a default `[]`, so a verifier payload that omits it still satisfies the runtime-injected `expected_output_schema`; the package-step callback then raises `ValueError("package verifier payload must define proposed_parameter_keys as a string list")` on `needs_rework` or `needs_replan` instead of looping normally. Reproduced with `PYTHONPATH=/home/rauter/autoloop_v3_bkp .venv/bin/python` by validating a payload without `proposed_parameter_keys` through `AdaptedExecutionPlanPayload`, then calling `on_package_adapted_execution_plan(...)`. Fix by making the schema and callback agree in one place: either require `proposed_parameter_keys` in `AdaptedExecutionPlanPayload`, or treat omission as `[]` in the callback and add a regression test for the rework/replan path.
