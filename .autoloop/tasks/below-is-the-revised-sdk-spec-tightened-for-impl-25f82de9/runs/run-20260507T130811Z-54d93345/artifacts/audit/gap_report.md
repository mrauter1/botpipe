# Original intent considered

- The immutable request snapshot, especially sections 7-9, 20, 23, 25, and 29.
- The authoritative raw log and decisions ledger, including decision blocks 3, 7, 8, 9, 11, and 12.
- The phase-local implement/test artifacts under `artifacts/implement/phases/*` and `artifacts/test/phases/*`.
- The final code in `autoloop/sdk.py`, `autoloop/core/context.py`, `autoloop/core/artifacts.py`, `autoloop/core/compiler.py`, `autoloop/core/engine.py`, and `autoloop/runtime/runner.py`.
- The final tests in `tests/unit/test_sdk_facade.py`, `tests/unit/test_validation.py`, `tests/unit/test_simple_surface.py`, `tests/runtime/test_workspace_and_context.py`, and `tests/contract/test_engine_contracts.py`.

# Clarifications / superseding decisions

- The SDK must stay a facade over `execute_workflow_package(...)` and must not add a public resume path or second engine surface.
- `message` and raw `Workflow.Input` fields must stay separate, and the composite `ctx.input` view must be the runtime-facing surface for message-plus-fields access.
- Bare unknown `input.*` placeholders should raise execution errors; `input.message` and declared `None` fields should render as empty strings.
- Sync active-event-loop normalization was intentionally scoped to bridge-backed SDK entrypoints `run(...)` and `step(...)`; decision block 9 explicitly excludes `llm(...)` and `classify(...)` from that coverage because they do not use the runtime bridge in this implementation.
- Decision block 8 intentionally introduced an omitted-message sentinel so normal runtime resume can still read the persisted request snapshot while SDK `client.run(..., None)` preserves a real `None`.

# Implemented behavior

- `autoloop/sdk.py` landed with `Autoloop`, `WorkflowResult`, `StepResult`, `ArtifactMap`, input handlers, SDK error types, and the public root exports requested in section 3.
- `Autoloop.run(...)` uses the existing runtime runner with internal pause/resume looping, typed-input validation, params coercion, provider-question policy adaptation, debug info, and artifact-handle construction.
- `Context`, `Engine`, branch/fan-in cloning, and runner propagation now carry `message` separately from raw typed input, and compile validation now rejects `Workflow.Input.message` with the spec text.
- Direct verification on 2026-05-07 with `.venv/bin/python -m pytest -q tests/unit/test_sdk_facade.py tests/unit/test_validation.py tests/unit/test_simple_surface.py tests/runtime/test_workspace_and_context.py tests/contract/test_engine_contracts.py -q` produced four failures. Two of those failures directly contradict the requested SDK/runtime contract and are the material gaps below.

# Unresolved gaps

1. `ctx.input.message` is still broken in runtime `ctx.*` placeholder rendering.
   Evidence:
   - `autoloop/core/artifacts.py:239-240` exposes `PromptContextView.input` as `self._context.input_fields` instead of the composite `self._context.input`.
   - `autoloop/core/artifacts.py:590-603` then rejects `ctx.input.message` when `context.input_fields is None`, and when typed input exists it looks for a real `message` field on the raw typed model.
   - `tests/contract/test_engine_contracts.py:8655-8725` expects both message-only and typed-input `ctx.input.message` rendering to succeed, and both tests fail in the current tree.
   Intent impact:
   - This violates request sections 7 and 9 (`ctx.input.message` must always exist, and runtime template rendering must support message-aware input views).
   - It also leaves the run-local known gap recorded in `artifacts/test/phases/sdk-facade/test_strategy.md` unresolved.

2. `Autoloop.step(...)` still rejects resolvable strict `ChildWorkflowStep` instances.
   Evidence:
   - Request section 23 accepts core `Step` instances that can compile inside a synthetic one-step workflow and only rejects child-workflow steps when the child reference is not directly resolvable.
   - `autoloop/sdk.py:849-852` calls `_ensure_child_workflow_resolvable(...)` and then unconditionally raises `SDKExecutionError("client.step(...) does not support strict child-workflow Step instances in the MVP")`.
   - A direct reproduction with `.venv/bin/python` and `ChildWorkflowStep(name="launch", workflow=Child)` returns that `SDKExecutionError` immediately even when `Child` is a real workflow class.
   - `tests/unit/test_sdk_facade.py:356-416` covers simple declarations, strict `PythonStep`, explicit route metadata, and branch-group rejection, but it does not cover the directly-resolvable strict child-workflow case the request leaves in scope.
   Intent impact:
   - The public `client.step(...)` surface is narrower than request section 23 allows.

# Differences justified by later clarification or analysis

- The implementation detail that preserves an omitted-message sentinel through runner/engine boundaries is justified by decision block 8 and is consistent with the request: it keeps normal runtime request-snapshot behavior without breaking SDK `message=None`.
- The active-event-loop normalization tests only cover `run(...)` and `step(...)`; decision block 9 explicitly justifies not extending that expectation to `llm(...)` and `classify(...)` in the current runtime.
- The worker-thread fallback for nested child workflow invocation from synchronous Python handlers is consistent with decision block 11 and preserves section 25 child-workflow semantics without adding public lifecycle APIs.

# Recommended next run

- Finish the composite runtime input contract in `autoloop/core/artifacts.py` so every `ctx.*` runtime-template path uses the composite `WorkflowInputView`, and rerun the failing `ctx.input.message` contract tests plus the adjacent SDK/runtime slice.
- Broaden `Autoloop.step(...)` to accept directly resolvable strict `ChildWorkflowStep` instances through the existing synthetic one-step workflow path, while keeping branch-group, worklist-scoped, and unresolved child-workflow declarations rejected.
- Add or extend SDK-facing tests so both gaps are covered at the public boundary and the focused regression slice passes cleanly.
