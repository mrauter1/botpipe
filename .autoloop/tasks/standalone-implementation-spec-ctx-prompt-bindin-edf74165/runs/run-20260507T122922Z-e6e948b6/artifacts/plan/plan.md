# `ctx.*` Runtime Context Prompt Bindings Plan

## Goal

- Add an explicit `ctx.*` runtime prompt namespace for message, request, typed input, state, and params without widening the template engine beyond safe dotted-path reads.
- Make the run-local `request.md` snapshot the only authoritative source for `ctx.message` and `ctx.request.text`, including resume behavior.
- Preserve existing non-`ctx` placeholder behavior, existing Python access to `ctx.input` / `ctx.state` / `ctx.params`, literal `workflow_step(message=...)` behavior unless placeholders are present, and literal `message_from` file/artifact reads.

## Code Surfaces

- `autoloop/core/context.py`: add `RequestContext`, `ctx.request`, `ctx.request_file`, `ctx.message`, and request-path derivation defaults that work for synthetic test contexts.
- `autoloop/core/context_placeholders.py` (new): own safe `ctx.*` segment validation, supported scalar roots, supported nested roots, and model-root validation helpers for reuse by compile-time and runtime code.
- `autoloop/runtime/runner.py` and `autoloop/core/branch_groups/context.py`: pass run-local and task-level request file paths through all root, branch, fan-in, and resume `Context(...)` construction paths.
- `autoloop/core/artifacts.py`: add lazy `PromptContextView`, `ctx` runtime placeholder resolution, scalar-only rendering/error handling, and explicit rejection of `ctx.*` inside artifact path templates.
- `autoloop/core/discovery.py` and `autoloop/core/prompt_validation.py`: validate supported `ctx.*` references and emit spec-matched failures for `{message}`, `{ctx}`, unsafe paths, bare model roots, and unknown fields.
- `autoloop/core/engine.py` and `autoloop/core/operations.py`: include `ctx` in runtime prompt replacement roots for provider-backed prompts, `produce_verify_step(...)`, `llm.step(...)`, `classify.step(...)`, and rendered `workflow_step(message=...)`.
- `docs/authoring.md` and `docs/architecture.md`: document `ctx.*` as the preferred authoring surface and restate immutable run-local request snapshot semantics.

## Milestones

### 1. Context Surface And Shared Contract

- Add lazy request/message accessors to `Context` and ensure `ctx.request.text == ctx.message`.
- Introduce one shared `context_placeholders` module so compile-time and runtime allowlists stay aligned.
- Propagate `request_file` and `task_request_file` through root, branch, and fan-in contexts without changing persistence layout or CLI behavior.

### 2. Runtime Rendering And Workflow Integration

- Resolve supported `ctx.*` placeholders through a restricted runtime view instead of exposing raw `Context`.
- Enforce safe-path validation, missing-input errors, scalar-only rendering, and explicit rejection of complex values for `ctx.*`.
- Reject `ctx.*` placeholders in artifact path templates before generic rendering.
- Render `workflow_step(message=...)` via runtime templating while keeping `message_from` content literal and unchanged.

### 3. Validation, Regression Coverage, And Docs

- Extend compile-time validation to accept supported `ctx.*` paths and reject unsupported/unsafe forms with stable messages.
- Extend runtime and contract tests for provider prompt rendering, operation prompt rendering, child workflow forwarding, message/input separation, resume stability, missing input, non-scalar failures, and no auto-injection.
- Update authoring docs/examples to prefer `ctx.*` over manual `request.md` copying when the goal is prompt access to request text.

## Interface Contract

- Python/system access: `ctx.message`, `ctx.request.text`, `ctx.request.file`, `ctx.request.task_file`, `ctx.request_file`, and existing typed `ctx.input`, `ctx.state`, `ctx.params`.
- Prompt access: support only the spec-listed `ctx.*` expressions plus the listed stable metadata fields; keep bare `{message}` unsupported.
- Runtime errors must remain explicit:
  - unreadable run request snapshot: `run request snapshot could not be read: <path>`
  - missing typed input for `ctx.input.<field>`: `ctx.input.<field> requires workflow input, but no input was provided`
  - non-scalar `ctx.*` value: `<placeholder_label> {<expression>} resolved to a non-scalar value`
  - unsafe `ctx.*` path: `<placeholder_label> {<expression>} is not a supported safe dotted path`

## Compatibility And Regression Controls

- Resume must continue to read the existing run-local `request.md`; it must not re-read mutable task metadata or fresh `RunnerOptions.message`.
- Child workflows must keep message and typed input separate: rendered `message` becomes the child run request snapshot, while `input` stays the typed `Input` model.
- Existing bare `{input.foo}`, `{state.foo}`, and `{params.foo}` behavior stays intact where already supported; `ctx.*` is additive and preferred.
- Existing `item`, `worklist`, `branch`, and `fan_in` prompt behavior must remain unchanged.
- Provider adapters should not need changes unless shared prompt plumbing proves incomplete in tests.

## Risk Register

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Request-file propagation is missed in one `Context(...)` path | `ctx.message` drifts between fresh runs, resume, branch/fan-in, or child execution | touch every root/cloned `Context(...)` site and cover with resume plus child-workflow tests |
| Compile-time/runtime allowlists diverge | a placeholder compiles but fails at runtime, or vice versa | centralize `ctx.*` validation rules in `autoloop/core/context_placeholders.py` and reuse them from both layers |
| `ctx.*` leaks into artifact path rendering | user request text can unexpectedly affect output paths | reject any `ctx.*` placeholder at the start of `resolve_artifact_template(...)` |
| Complex values stringify silently | provider prompts become unstable and behavior widens unintentionally | apply scalar-only rendering for `ctx.*` and keep existing non-`ctx` rendering rules untouched |
