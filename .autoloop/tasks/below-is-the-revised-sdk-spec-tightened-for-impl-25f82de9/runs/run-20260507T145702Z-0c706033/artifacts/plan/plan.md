# Remaining SDK/Runtime Contract Gap Plan

## Goal

- Close only the follow-up gaps left after the earlier SDK/runtime work: make every `ctx.input.message` template path use the composite runtime input view, allow directly resolvable strict `ChildWorkflowStep` through `client.step(...)`, and lock both with focused regression coverage.

## Current Code Read

- `autoloop/core/context.py` already exposes composite `Context.input` and raw `Context.input_fields`.
- `autoloop/core/artifacts.py` still resolves `ctx.input.*` through `PromptContextView.input -> context.input_fields` and rejects all `ctx.input.*` when `input_fields` is `None`; this is the remaining cause of `ctx.input.message` template drift.
- `autoloop/core/engine.py` already routes both runtime template rendering and `workflow_step(message=...)` through `render_runtime_template(...)`, so the shared `ctx` resolver is the correct single fix point.
- `autoloop/sdk.py` already compiles strict core `Step` instances through `_build_synthetic_step_workflow(...)`; the remaining SDK gap is the explicit `ChildWorkflowStep` MVP rejection after `_ensure_child_workflow_resolvable(...)`.
- `tests/unit/test_primitives_and_stores.py`, `tests/contract/test_engine_contracts.py`, and `tests/unit/test_sdk_facade.py` already cover the adjacent surfaces. Some unit expectations are stale because they still assume `ctx.input.message` can come from a typed `Input.message` field, which the accepted contract already forbids.

## Implementation Milestone

### 1. Composite `ctx.input` Rendering

- In `autoloop/core/artifacts.py`, make `PromptContextView.input` expose `context.input`, not `context.input_fields`.
- Narrow the `ctx.input.*` missing-input guard so `ctx.input.message` is always allowed and reads the runtime message, while other `ctx.input.<field>` accesses still require `input_fields`.
- Keep bare `input.*` placeholder behavior unchanged so only the `ctx.*` path is redirected to the composite view.

### 2. Direct Strict `ChildWorkflowStep` Support In `client.step(...)`

- In `autoloop/sdk.py`, keep branch-group, scoped-step, and unresolved-child preflight rejections intact.
- Remove the special-case MVP rejection for strict `ChildWorkflowStep` once `_ensure_child_workflow_resolvable(...)` passes, so the declaration continues through the existing synthetic core-workflow execution path.
- Do not add a second execution path or relax child-workflow resolution rules.

### 3. Focused Regression Slice

- Update runtime/unit coverage to assert `ctx.input.message` resolves from the runtime message both with no typed input and with typed input present, including runtime-template and workflow-step child-message surfaces.
- Replace stale typed-`Input.message` expectations with models that keep typed fields separate from the runtime message.
- Add SDK coverage for successful strict `ChildWorkflowStep` execution via `client.step(...)` and for unresolved child-workflow failure wrapping.
- Rerun the focused slice spanning `tests/unit/test_primitives_and_stores.py`, `tests/contract/test_engine_contracts.py`, and `tests/unit/test_sdk_facade.py`.

## Interface And Invariants

- `ctx.input.message` is always the runtime message view exposed by `Context.input`, never a typed `Workflow.Input.message` field.
- When typed input exists, `ctx.input.<field>` still resolves declared typed fields and `ctx.input_fields` remains the raw typed model.
- Bare `input.message` compatibility stays separate and unchanged.
- `client.step(...)` may now accept only directly resolvable, unscoped strict `ChildWorkflowStep` declarations; unresolved child references must still raise `SDKExecutionError`, and branch-group or worklist-scoped declarations remain rejected.

## Compatibility / Regression Controls

- No public API expansion beyond the requested acceptance of strict `ChildWorkflowStep` on the existing `client.step(...)` surface.
- No change to runtime child invocation semantics, artifact-path rules, or bare non-`ctx` placeholder rendering.
- The fix should stay localized to the shared runtime template resolver so artifact templates and workflow-step child messages pick up the same behavior automatically.

## Validation / Rollback

- Validation should prove:
  - `render_runtime_template(..., replace_roots={"ctx"})` returns the runtime message for `ctx.input.message` with and without typed input.
  - `workflow_step(message="...{ctx.input.message}...")` forwards the runtime message, not typed input, into the child request snapshot.
  - `client.step(ChildWorkflowStep(...))` completes through the synthetic one-step workflow when the child reference resolves.
  - `client.step(ChildWorkflowStep(workflow="missing"))` still fails with SDK-owned unresolved-reference messaging.
- Rollback is local: revert `autoloop/core/artifacts.py`, `autoloop/sdk.py`, and the focused regression tests together if the shared resolver change unexpectedly alters unrelated placeholder behavior.

## Risk Register

| Risk | Impact | Mitigation |
| --- | --- | --- |
| `ctx.input` fix accidentally changes bare `input.*` semantics | existing artifact/prompt compatibility regresses | keep the composite-view change inside the `ctx` resolver only and preserve `_resolve_input_placeholder(...)` behavior |
| Allowing strict child steps over-accepts unsupported declarations | `client.step(...)` silently accepts branch/scoped/unresolved child cases | keep existing branch-group and scope guards, and preserve `_ensure_child_workflow_resolvable(...)` before the synthetic workflow path |
| Tests keep stale `Input.message` assumptions | follow-up work can reintroduce the wrong contract later | replace those expectations in both unit and contract coverage with runtime-message assertions |
