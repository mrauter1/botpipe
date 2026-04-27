# Implementation Notes

- Task ID: recursive-framework-evolution-20260427t144615-bootstrap
- Pair: implement
- Phase ID: engine-hooks-workflow-step
- Phase Directory Key: engine-hooks-workflow-step
- Phase Title: Engine Hooks And WorkflowStep
- Scope: phase-local producer artifact

## Files changed
- `core/steps.py`
- `core/compiler.py`
- `core/engine.py`
- `core/extensions.py`
- `core/validation.py`
- `core/__init__.py`
- `workflow/__init__.py`
- `runtime/tracing.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_runtime_tracing.py`
- `tests/unit/test_simple_surface.py`

## Symbols touched
- `core.steps.AfterHookResult`
- `core.steps.Step.__init__`, `PairStep.__init__`, `LLMStep.__init__`, `SystemStep.__init__`
- `core.compiler.CompiledStep`, `CompiledRoute`, `_compile_steps`, `_compile_route`
- `core.engine.Engine._execute_step`, `_execute_pair_step`, `_execute_llm_step`, `_run_before_hook`, `_run_after_hook`, `_normalize_after_hook_result`, `_finalize_step_result`
- `core.validation._lower_simple_steps`, `_validate_step_hooks`
- `core.extensions.StepFinish`
- `runtime.tracing.RuntimeTraceWriter._write_step_finished`

## Checklist mapping
- Plan item 10: implemented step-level `before` / `after` compilation, runtime execution ordering, and after-hook route override normalization.
- Plan item 11: promoted lowered simple child-workflow nodes to compiled `kind="workflow"` and added explicit engine handling for workflow-step hook ordering.
- Plan item 13: added focused contract/runtime/unit regressions for provider hooks, system hooks, workflow-step loops, invalid overrides, final-route enforcement, and trace metadata.

## Assumptions
- This phase keeps simple `workflow_step(...)` lowering on the existing generated `ctx.invoke_workflow(...)` handler path from the prior phase instead of replacing it with a second child-workflow execution implementation.
- Hook signature flexibility is limited to the arities described in the request examples: `before` accepts 1 or 2 positional args; `after` accepts 2, 3, or 4 positional args.

## Preserved invariants
- Provider retries still operate only on provider-attributable failures.
- Required input enforcement remains target-step-owned through `step.requires`.
- Final route validation still happens before route effects and checkpoint transition.
- Existing simple child-workflow message/output lowering remains deterministic and filesystem-backed.

## Intended behavior changes
- Steps may now declare `before` / `after` hooks through both strict constructors and lowered simple declarations.
- `after` hooks may override the selected route via `str`, `Event`, or `AfterHookResult`, and final artifact obligations are enforced against the final route.
- Lowered simple workflow steps now compile as `kind="workflow"` instead of `kind="system"` for engine/tracing purposes.
- Step-finish trace records can include hook route-override metadata.
- Route handoffs targeted at lowered workflow steps are now explicitly dropped, matching prior system-step behavior until child-workflow handoff delivery is implemented.

## Known non-changes
- No second child-workflow engine was added.
- `autoloop.simple.workflow_step(...)` still uses the generated handler compatibility path installed during simple lowering.
- Route handoff scheduling still flows through existing `Handoff` effects / event handoff behavior.
- Child-workflow invocations still do not accept queued route handoff text as an additional message channel in this phase.

## Expected side effects
- Hook-driven route overrides that introduce new required outputs now fail against the final route and are not retried as provider failures.
- Runtime extensions and trace consumers now receive `StepFinish` events with optional `hook_route_override_from` / `hook_route_override_to` fields.

## Validation performed
- `.venv/bin/pytest tests/unit/test_simple_surface.py tests/contract/test_engine_contracts.py tests/runtime/test_runtime_tracing.py -q`

## Deduplication / centralization
- Centralized hook normalization and final-route enforcement in `core.engine` so provider, system, and workflow-step paths share the same finalization logic.
