# Remaining-Delta Implementation Plan

## Contract
- Implement the pasted remaining-delta spec as written with no compatibility shims, migration aliases, or silent coercions.
- Keep the public authoring/compiler path derived from step-local routes only; removed public surfaces must fail fast at declaration or validation time.
- Guarantee `ctx.step_item_state` for scoped steps and add a small built-in runtime-owned `ctx.item_state` model for active scoped items.
- The built-in `ctx.item_state` contract is `status`, `last_step`, and `last_route`; those fields are runtime-owned and read-only, while custom declared item-state fields remain mutable.
- Preserve mutated state, step state, scoped state, worklist selection, and sessions on every failure path by checkpointing current runtime data instead of restoring prior snapshots.

## Milestones
### 1. Public Surface And Compiler Cleanup
Scope:
- Remove public `on_route` and internal `on_route_hook` from steps, compiler output, engine execution, topology artifacts, capability payloads, docs, and tests.
- Remove legacy public/simple surfaces: auto-installed `on_<step>` handlers, class-level public `transitions` / `flow`, class-level outcome middleware on the public path, and old declaration markers based on dunder flags.
- Rename internal/public payload vocabulary to `writes`, `producer_writes`, and `verifier_writes` only; remove `outputs`, `review_outputs`, and `produces` aliases from declarations, lowering, and debug payloads.
Primary files:
- `autoloop/simple.py`
- `autoloop/core/discovery.py`
- `autoloop/core/compiler.py`
- `autoloop/core/topology.py`
- `autoloop/core/routes.py`
- `autoloop/core/steps.py`
- `autoloop/runtime/static_graph.py`
- `autoloop/core/workflow_capabilities.py`
Regression controls:
- Removed public surfaces fail during construction/validation instead of silently lowering to legacy behavior.
- Public/simple discovery changes must not weaken strict/internal authoring unless the path is explicitly isolated from the public compiler surface.
- Route effects stay in place until helper parity exists; deletion and rejection move to the worklist-helper milestone.

### 2. Hook And Runtime-Control Unification
Scope:
- Enforce one public hook signature, `hook(ctx)`, across `before`, `after`, pair lifecycle hooks, and route `on_taken`.
- Introduce one normalized internal hook result model and remove `AfterStepResult`, hook state replacement returns, positional arity overloads, and multi-form python-step returns.
- Allow `before`, `before_producer`, and `before_verifier` to short-circuit with route tags or direct controls; allow `after_producer`, `after_verifier`, and `after` to follow the same normalized result rules.
- Refactor finalization around explicit structures instead of tuple/flag plumbing, and move hook/finalization logic into `HookRunner`, `RouteFinalizer`, and `StepDispatcher` as real owners rather than wrappers.
Interfaces:
- `HookResult(event: Event | None = None, control: RequestInput | Goto | Fail | None = None)`
- `python_step` handler returns: `None | str | Event | RequestInput | Goto | Fail`
- Runtime validation remains phase-independent and only checks route/control validity against the current step and workflow topology.
Primary files:
- `autoloop/core/engine.py`
- `autoloop/core/engine_collaborators.py`
- `autoloop/core/hook_validation.py`
- `autoloop/core/compiler.py`
- `autoloop/core/steps.py`
- `autoloop/core/primitives.py`
Regression controls:
- Hook-originated short-circuits must skip provider execution and provider retry when no provider turn ran.
- Only successfully finalized route-based outcomes may update built-in finalized-route fields.

### 3. Scoped State And Worklist Runtime Helpers
Scope:
- Guarantee `ctx.step_item_state` on every scoped step by always materializing the built-in runtime fields and layering optional custom fields on top.
- Add a built-in runtime-owned `ctx.item_state` model for active scoped items with `status`, `last_step`, and `last_route`, and layer optional declared custom item-state fields on top.
- Add the public worklist runtime surface: `ctx.worklist(name)`, `ctx.worklists.<name>`, `ctx.current_worklist`, and `WorklistRuntimeView`.
- Replace route effects with helper-driven selection/status mutation and route/on_taken-driven control flow, then delete route-effect declarations and engine execution only after helper parity is covered by tests.
Interfaces:
- `WorklistRuntimeView.selection`, `.current`, `.current_id`, `.current_index`, `.item_ids`, `.is_exhausted`
- `refresh()`, `set_current_status(status)`, `reset_current_status()`, `advance()`, `advance_or(exhausted=...)`, `validate()`, `validation_error()`
- Built-in `ctx.item_state` fields: `status`, `last_step`, `last_route`
- Helper mutations emit runtime events and are checkpointed without automatic rollback.
Primary files:
- `autoloop/core/context.py`
- `autoloop/core/worklists.py`
- `autoloop/core/engine.py`
- `autoloop/core/step_state.py`
- `autoloop/runtime/tracing.py`
- `autoloop/core/history.py`
Regression controls:
- Helper methods mutate selection/status only; they must never auto-route.
- Mutable-source persistence remains source-owned, but in-memory runtime selection and checkpoint state must reflect the helper mutation immediately.

### 4. Structured Failures, Trace/History, And Optimizer Alignment
Scope:
- Replace dynamic exception metadata mutation/readback with typed execution errors carrying structured failure context, retry attribution, and preserved runtime snapshots through explicit fields.
- Remove `getattr(..., "failure_context")` style recovery paths from engine, operation recording, and related helpers.
- Extend trace/history to represent hook-selected direct controls, no-provider attempts, target steps, pending input ids, and route/control source attribution.
- Align runtime history and optimizer vocabulary around terminal `AWAIT_INPUT`, route tag `"question"`, and status `"awaiting_input"`, while treating direct controls separately from provider failures.
- Move state/session/checkpoint/workflow-invocation ownership into the named collaborators so `Engine` becomes orchestration-only.
Primary files:
- `autoloop/core/errors.py`
- `autoloop/core/engine.py`
- `autoloop/core/engine_collaborators.py`
- `autoloop/core/operations.py`
- `autoloop/core/history.py`
- `autoloop/runtime/tracing.py`
- `autoloop/runtime/runner.py`
- `autoloop_optimizer/*.py`
Regression controls:
- Failure checkpoints must persist current mutated state/session/worklist data for hook failures, route validation failures, artifact failures, provider failures, and direct-control validation failures.
- History derivation must not assume every finished step has a final route or that every non-success outcome is provider-attributable.

### 5. Documentation And Test Migration
Scope:
- Update docs to show only final hook style, final hook return model, direct-control semantics, and worklist helper patterns.
- Remove docs and examples for `AfterStepResult`, positional hooks, step-level `on_route`, route effects, class-level public transitions, and old `outputs` vocabulary.
- Update and expand unit, contract, runtime, static-graph, history, and optimizer tests to cover the new control model and intentional public breakages.
Primary files:
- `docs/authoring.md`
- `docs/workflows/*.md`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_validation.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_history.py`
- `tests/runtime/test_runtime_tracing.py`
- `tests/runtime/test_runtime_static_graph.py`
- relevant optimizer/runtime integration suites
Regression controls:
- Replace removed-surface tests with fail-fast coverage and equivalent `on_taken`/helper-based workflows.
- Keep golden/integration coverage for checkpoint persistence, pending input resume, and scoped worklist progression.

## Validation Sequence
1. Public-surface compile/validation tests after milestone 1 to ensure removed APIs fail before runtime execution changes land.
2. Engine/contract tests after milestone 2 for hook short-circuiting, python-step control returns, retry attribution, and finalized-route state invariants.
3. Scoped worklist/runtime tests after milestone 3 for helper mutation semantics, checkpointing, trace events, and read-only runtime-owned fields.
4. History, tracing, optimizer, and run-record tests after milestone 4 for direct controls, no-provider attempts, and status normalization.
5. Full docs/example/test pass after milestone 5 to remove stale references and ensure the repo advertises only the final authoring model.

## Compatibility And Intentional Breaks
- Removed immediately and without aliases: `on_route`, `AfterStepResult`, multi-arity hooks, hook state returns, python-step tuple/BaseModel returns, `outputs` / `review_outputs` / `produces` vocabulary, auto-installed `on_<step>` handlers, and public class-level legacy flow surfaces.
- Route effects remain temporarily supported only until worklist-helper parity lands; once phase 3 is complete they are removed without compatibility aliases.
- The clarified scoped item-state contract is now an intentional public change: active scoped items always expose built-in `ctx.item_state` runtime fields `status`, `last_step`, and `last_route`.
- Public topology/debug payloads, static graph artifacts, and capability inspection must emit only the final vocabulary and hook model in the same turn as the runtime/compiler changes.

## Risk Register
- R1: Hook/finalization refactor can regress retry behavior, pending input handling, or built-in route state updates.
  Mitigation: land compile-time/public-surface removals first, then add hook/control tests before removing old normalization branches.
- R2: Route-effect removal can desynchronize worklist selection, mutable-source persistence, and checkpoint payloads.
  Mitigation: add `WorklistRuntimeView` and parity coverage first, switch equivalent runtime flows to helpers, then delete route-effect declarations and execution paths in the same milestone.
- R3: Failure-model cleanup can break history, tracing, and optimizer consumers that still read dynamic exception metadata.
  Mitigation: update typed error production and all consumers in the same milestone; remove `getattr` readers only after typed fields are wired end-to-end.
- R4: Public-surface cleanup touches docs, discovery, capability payloads, and tests at once.
  Mitigation: keep all removed-surface references as explicit fail-fast tests or doc updates in the same phase to avoid hybrid contracts.
- R5: Collaborator refactor can become wrapper churn without reducing coupling.
  Mitigation: move existing logic directly into the named collaborator classes already present and avoid introducing additional generic abstraction layers.
