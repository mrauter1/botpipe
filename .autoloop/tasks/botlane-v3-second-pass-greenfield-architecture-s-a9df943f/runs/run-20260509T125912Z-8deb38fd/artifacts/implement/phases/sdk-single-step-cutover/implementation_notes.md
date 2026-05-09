# Implementation Notes

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: implement
- Phase ID: sdk-single-step-cutover
- Phase Directory Key: sdk-single-step-cutover
- Phase Title: SDK Single Step Cutover
- Scope: phase-local producer artifact

## Files changed

- `botlane/sdk.py`
- `botlane/runtime/runner.py`
- `botlane/core/engine.py`
- `tests/unit/test_sdk_facade.py`
- `tests/contract/test_single_step_plan_equivalence.py`
- `tests/contract/test_sdk_single_step_execution.py`

## Symbols touched

- `Botlane.run`
- `Botlane.step`
- `Botlane._run_compiled_plan`
- `_build_single_step_execution_plan`
- `_build_single_step_plan`
- `_build_single_step_workflow_plan`
- `_single_step_workflow_reference`
- `execute_workflow_plan`
- `Engine._run_workflow_step`
- `Engine._write_workflow_step_outputs`

## Checklist mapping

- Phase 7 / AC-1: removed `Botlane.step(...)` synthetic-workflow fallback and `client.run(...)` delegation; the SDK now builds a direct `SingleStepPlan` plus one-step `WorkflowPlan` and executes that plan through the normal runner.
- Phase 7 / AC-2: preserved helper-facade behavior for `Botlane.step(...)`, `prompt_step(...)`, `produce_verify_step(...)`, `python_step(...)`, and `workflow_step(...)`; updated tests to cover direct single-step execution and the public helper contracts.

## Assumptions

- A private identity workflow class is acceptable for `WorkflowPlan.workflow_cls` and runtime metadata as long as `Botlane.step(...)` no longer compiles or runs a synthetic workflow fallback path.

## Preserved invariants

- `Botlane.step(...)` still returns `StepResult(value=None, workflow_result=...)`.
- Invocation-local policy layering still does not mutate the supplied step/declaration object.
- Pause/resume, provider-questions defaulting, retention, artifact handling, and SDK error wrapping still use the shared SDK run loop.
- Child-workflow step behavior remains routed through typed `ChildWorkflowStepPlan` data without reintroducing authored-step backreferences.

## Intended behavior changes

- Internal only: one-step SDK execution now uses the canonical direct plan path instead of building and running a synthetic workflow fallback.

## Known non-changes

- Public SDK signatures and helper entrypoints are unchanged.
- `Botlane.run(...)` still uses normal workflow reference resolution and compilation.
- No public exports were changed for this phase.

## Expected side effects

- One-step runs now persist workflow metadata/topology from a directly-built one-step `WorkflowPlan`.
- Engine child-workflow output writing now supports both authored-step mappings and plan-time `ArtifactId` write tuples.

## Validation performed

- `python3 -m py_compile botlane/sdk.py botlane/runtime/runner.py tests/unit/test_sdk_facade.py tests/contract/test_single_step_plan_equivalence.py tests/contract/test_sdk_single_step_execution.py`
- `.venv/bin/python -m pytest -q tests/unit/test_sdk_facade.py tests/contract/test_single_step_plan_equivalence.py tests/contract/test_sdk_single_step_execution.py`
- `.venv/bin/python -m pytest -q tests/contract/engine/test_child_workflows.py`

## Deduplication / centralization decisions

- Centralized the shared SDK execution loop in `Botlane._run_compiled_plan(...)` so `Botlane.run(...)` and `Botlane.step(...)` keep identical pause/resume, retention, and error-wrapping behavior while using different plan-construction paths.
