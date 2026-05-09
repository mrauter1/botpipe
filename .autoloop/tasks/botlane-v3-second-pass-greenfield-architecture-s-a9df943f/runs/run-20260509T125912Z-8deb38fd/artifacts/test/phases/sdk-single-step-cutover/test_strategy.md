# Test Strategy

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: test
- Phase ID: sdk-single-step-cutover
- Phase Directory Key: sdk-single-step-cutover
- Phase Title: SDK Single Step Cutover
- Scope: phase-local producer artifact

## Behavior-to-coverage map

- Compiler-owned single-step planning:
  `tests/unit/test_sdk_facade.py::test_sdk_single_step_workflow_plan_delegates_to_compiler_builder`
  asserts `sdk._build_single_step_workflow_plan(...)` delegates to the compiler helper and forwards inferred input/params models plus explicit routes.
- Canonical one-step architecture:
  `tests/contract/test_single_step_plan_equivalence.py::test_sdk_module_no_longer_exposes_synthetic_step_workflow_builder`
  and the direct plan-build tests keep the synthetic workflow fallback removed and `SingleStepPlan` as the sole path.
- Preserved route override behavior:
  `tests/unit/test_sdk_facade.py::test_sdk_step_preserves_explicit_routes_for_core_steps`
  checks explicit `FINISH`, `AWAIT_INPUT`, `FAIL`, and `SELF` lowering for core steps.
- Preserved simple/core pair self-loop behavior:
  `tests/contract/test_single_step_plan_equivalence.py::test_single_step_workflow_plan_lowers_simple_pair_rework_to_current_step`
  and `tests/unit/test_sdk_facade.py::test_sdk_produce_verify_step_defaults_to_rework_self_loop`
  pin `needs_rework` lowering to the current step instead of a literal `SELF` target.
- Preserved SDK helper and result contracts:
  `tests/unit/test_sdk_facade.py`
  and `tests/contract/test_sdk_single_step_execution.py`
  cover `Botlane.step(...)`, `prompt_step(...)`, `produce_verify_step(...)`, `python_step(...)`, and `workflow_step(...)`, including policy layering, `StepResult(value=None, workflow_result=...)`, and public helper parity.
- Adjacent child-workflow regression surface:
  `tests/contract/engine/test_child_workflows.py`
  stays in the focused run because the phase still routes child-workflow steps through the shared one-step planning and typed child-workflow execution path.

## Preserved invariants checked

- Invocation-local policy does not mutate the supplied step object.
- Public route authoring and runtime lowering semantics remain unchanged.
- `Botlane.step(...)` still returns a `WorkflowResult` passthrough via `StepResult.workflow_result`.
- Child-workflow one-step execution remains resolvable and executable.

## Edge cases and failure paths

- Explicit route overrides with `SELF` and `Route(target=SELF, ...)`.
- Simple produce/verify default `needs_rework` self-loop lowering.
- Compiler-helper delegation with inferred dynamic params models from mapping input.

## Known gaps

- This phase strategy keeps to the focused SDK single-step and adjacent child-workflow suites; it does not add new full-suite coverage outside the phase contract.
- The delegation test pins the SDK boundary, not the internal implementation details of compiler helper construction.

## Stability notes

- Added tests are deterministic and use local fake/scripted providers or monkeypatched helper calls only.
- No timing, network, or nondeterministic ordering dependencies were introduced.
