# SDK Facade Plan

## Scope
- Add a new public SDK facade in `autoloop/sdk.py` and re-export it from `autoloop/__init__.py`.
- Keep the SDK as a thin synchronous wrapper over the existing filesystem runtime and `execute_workflow_package(...)`.
- Change runtime context input handling so `message` and typed `Workflow.Input` remain separate while exposing a composite `ctx.input`.
- Add SDK-only pause handling, input handlers, result models, standalone `llm`/`classify`, and synthetic one-step execution.
- Make the sync SDK entrypoints fail with SDK-owned errors, including the active-event-loop case where sync execution cannot proceed.
- Extend tests for SDK behavior, context propagation, prompt rendering, pause/resume, and persisted metadata separation.

## Repository Seams
- `autoloop/runtime/runner.py` already owns `RunnerOptions`, `execute_workflow_package(...)`, `message`, `workflow_input`, child invocation, and pending-input metadata.
- `autoloop/core/context.py` currently derives `ctx.message` from `request.md` and exposes raw `workflow_input` as `ctx.input`.
- `autoloop/core/branch_groups/context.py` clones child contexts with `workflow_input=parent.input`, which must change once `ctx.input` becomes a composite view.
- `autoloop/core/artifacts.py` owns prompt/artifact template rendering and safe `ctx.*` placeholder resolution.
- `autoloop/core/compiler.py` and `autoloop/core/discovery.py` own `Workflow.Input` compilation and validation.
- `autoloop/core/operations.py` already provides `llm_call(...)` and `classify_call(...)` for standalone SDK operations.

## Implementation Milestones
### 1. Runtime input contract refactor
- Add `WorkflowInputView` in `autoloop/core/context.py`.
- Extend `Context(...)` with `message: str | None`, store `_message` and `_input_fields`, expose `message`, `input_fields`, and composite `input`.
- Update all root/resume/step/branch/fan-in `Context(...)` construction sites to pass `message` and raw typed input separately.
- Update `Engine.run(...)` and `Engine.resume(...)` signatures to accept and propagate `message`.
- Keep persisted `request.md` semantics intact by passing the run-local request text back into resumed/root contexts; `ctx.message` must still match `ctx.request.text` in normal runtime flows.

### 2. Workflow.Input validation and rendering
- Add compile/definition validation that rejects `Workflow.Input.message` with the exact spec error text.
- Keep `CompiledWorkflow.input_model` as the source of truth; add SDK-side exact-instance validation instead of weakening runtime child-workflow compatibility.
- Update runtime placeholder resolution so `ctx.input.message` works through the composite view and `None` values render as empty strings.
- Extend runtime template support for `input.message` and typed input fields where runtime templates currently resolve workflow input values; do not regress existing `ctx.*` prompt/message behavior.
- Preserve metadata separation: `message` stays in task/run request snapshots, `workflow_input` stores typed fields only, `workflow_params` stays independent.

### 3. SDK facade and pause loop
- Create `autoloop/sdk.py` with:
  - `Autoloop`
  - `WorkflowResult`, `StepResult`, `ArtifactMap`, `InputRequest`, `HandledInput`, `SDKDebugInfo`
  - `AutoloopSDKError`, `WorkflowInputError`, `WorkflowParameterError`, `InputRequired`, `TooManyPauses`, `InputResponseValidationError`, `SDKExecutionError`
  - `ConsoleInput`, `StaticInput`, `MappingInput`, `BestSuppositionInput`
- `Autoloop.__init__` should resolve:
  - explicit `LLMProvider` objects directly
  - provider-name strings through existing runtime config/backend resolution
  - `model` / `model_effort` overrides via cloned runtime provider config
  - `runtime_config`, `provider_policy_config`, and `state_dir` defaults without inventing a second provider stack
- `Autoloop.run(...)` should:
  - resolve/compile workflow first
  - coerce typed input and params through dedicated SDK helpers
  - generate an internal SDK task id using `sdk-<workflow-name>-<utc-yyyymmddThhmmssZ>-<8hex>`, retrying on collision before creating runtime workspaces
  - loop via `execute_workflow_package(...)` using one stable `task_id`, a captured `run_id`, stable `message`, `workflow_input`, and `workflow_params`
  - build `InputRequest` from checkpoint pending-input metadata first, then question-style event fallback
  - serialize handler responses per spec and wrap validation failures in `InputResponseValidationError`
- Sync SDK entrypoints must not leak the raw `run_awaitable_sync(...)` bridge error. `run(...)`, `step(...)`, `llm(...)`, and `classify(...)` should raise `SDKExecutionError` with explicit guidance when called inside an active event loop and sync execution cannot proceed.
- Provider-question policy should be set by one helper that adapts `provider_questions` to runtime interaction policy / `RuntimeConfig.full_auto` without altering unrelated runtime behavior.
- `SDKDebugInfo` should be populated directly from the resolved run workspace and include the required path/debug fields (`task_id`, `run_id`, `task_dir`, `workflow_dir`, `run_dir`, `events_file`, `trace_file`, `checkpoint_file`).

### 4. Standalone operations, synthetic steps, and verification
- `Autoloop.llm(...)` / `classify(...)` should delegate to `llm_call(...)` / `classify_call(...)` with the resolved SDK provider and an SDK-owned operation replay folder.
- `Autoloop.step(...)` should synthesize an internal one-step workflow class rather than bypassing the engine.
- When `typed_input` is supplied to `Autoloop.step(...)`, the synthetic workflow must set `Input = type(typed_input)` so the same typed-input validation path is exercised as `Autoloop.run(...)`.
- If the supplied declaration has no terminal route, the synthetic workflow must inject the default `done -> FINISH` route before compilation so supported one-step declarations terminate without extra author ceremony.
- Accept simple named declarations directly; accept core `Step` only when it compiles cleanly in the synthetic workflow; reject worklist-scoped, branch-group, unsupported artifact-dependent, and unresolved child-workflow cases early with `SDKExecutionError`.
- Add focused SDK tests, plus runtime regression tests for:
  - `ctx.message`, `ctx.input.message`, `ctx.input_fields`
  - persisted `workflow_input` excluding `message`
  - pause/resume stability across internal SDK resumes
  - provider-questions defaults and explicit overrides
  - artifact and prompt rendering with message/input separation
  - sync SDK entrypoints raising `SDKExecutionError` inside active event loops when sync bridging is unavailable
  - synthetic step wrappers honoring typed input and implicit `done -> FINISH`

## Interface Notes
- Public SDK `typed_input` must be `None` or `type(typed_input) is compiled.input_model`; no `dict`, no subclasses, no keyword expansion.
- Public SDK `params` may remain mapping or `Workflow.Params` instance because runtime already has a parameter coercion path.
- Internal child workflow invocation keeps accepting `dict` input for compatibility; the strict typed-input rule applies only to the new SDK surface.
- `ArtifactMap` should wrap resolved artifact handles from `compiled.artifact_items(authoritative=False)` and expose attribute access plus `require(...)`.
- `WorkflowResult.debug` is the only public path for `task_id` / `run_id`.
- `WorkflowResult.debug` must carry the full `SDKDebugInfo` contract, not just ids, because the request explicitly treats filesystem paths as troubleshooting output.

## Compatibility / Intentional Breaks
- Intentional authoring break required by spec: workflows declaring `Workflow.Input.message` must now fail validation.
- No public `resume`, checkpoints, event browsing, or task/run lifecycle APIs should be introduced.
- Existing runtime runner/CLI behavior should remain intact; SDK behavior must layer on top of the runner, not fork it.
- Preserve current child-workflow runtime semantics and persisted folder layout; MVP keeps on-disk artifacts and run folders.
- Sync MVP compatibility note: when called inside an active event loop, sync SDK methods must raise a clear `SDKExecutionError` instead of exposing lower-level runtime bridge errors. Async SDK variants may stay deferred, but the sync error path must be intentional and tested.

## Regression Controls
- Invariants:
  - `ctx.message == ctx.input.message`
  - `ctx.input_fields` is the raw typed model or `None`
  - `ctx.input` is never written back into persisted `workflow_input`
  - internal SDK resumes reuse the same `task_id`, `run_id`, `message`, `workflow_input`, and `workflow_params`
  - direct Python `RequestInput(...)` pauses still work even when provider questions are disabled
- Test surfaces:
  - `tests/runtime/test_workspace_and_context.py`
  - `tests/unit/test_primitives_and_stores.py`
  - `tests/unit/test_simple_surface.py`
  - new SDK-focused test module(s) for facade, errors, handlers, and operations
  - active-event-loop contract coverage for each sync SDK entrypoint
  - synthetic step coverage for implicit terminal routing and typed-input injection
- Rollback:
  - revert SDK exports and `autoloop/sdk.py`
  - revert context composite-input changes as one unit with associated rendering/validation updates
  - preserve runtime metadata layout if partial work must be backed out

## Risk Register
- Risk: context clones accidentally pass the composite `ctx.input` where raw typed input is required.
  Mitigation: update branch/fan-in/root/resume clones together and add explicit regression tests around `ctx.input_fields`.
- Risk: provider-question policy helper changes legacy full-auto behavior outside the SDK.
  Mitigation: keep policy adaptation SDK-local and retain existing runner defaults for non-SDK callers.
- Risk: prompt/template rendering changes break existing `ctx.*` placeholders or runtime artifact paths.
  Mitigation: extend current resolver paths instead of replacing them; keep existing `ctx.*` tests green and add new `input.message` coverage.
- Risk: sync SDK wrappers leak lower-level event-loop bridge failures and create a public contract mismatch in notebooks or async hosts.
  Mitigation: normalize that failure path at the SDK boundary and add explicit acceptance tests for `run`, `step`, `llm`, and `classify`.
- Risk: synthetic step workflows accept declarations that need workflow-level features not present in the wrapper.
  Mitigation: reject unsupported declarations early, inject only the two requested synthesis defaults (`Input = type(typed_input)` and `done -> FINISH`), and keep MVP acceptance narrow.
