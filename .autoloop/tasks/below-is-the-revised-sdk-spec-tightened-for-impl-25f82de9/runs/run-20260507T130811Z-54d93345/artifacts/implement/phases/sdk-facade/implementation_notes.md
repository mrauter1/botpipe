# Implementation Notes

- Task ID: below-is-the-revised-sdk-spec-tightened-for-impl-25f82de9
- Pair: implement
- Phase ID: sdk-facade
- Phase Directory Key: sdk-facade
- Phase Title: Add SDK Facade
- Scope: phase-local producer artifact

## Files changed
- `autoloop/sdk.py`
- `autoloop/core/engine.py`
- `autoloop/core/context.py`
- `autoloop/core/artifacts.py`
- `autoloop/core/discovery.py`
- `autoloop/core/compiler.py`
- `autoloop/runtime/runner.py`
- `tests/unit/test_sdk_facade.py`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_validation.py`
- `tests/runtime/test_workspace_and_context.py`
- `tests/contract/test_engine_contracts.py`

## Symbols touched
- `Autoloop`, `WorkflowResult`, `StepResult`, `ArtifactMap`
- `InputRequest`, `HandledInput`, `SDKDebugInfo`
- `AutoloopSDKError`, `WorkflowInputError`, `WorkflowParameterError`, `InputRequired`, `TooManyPauses`, `InputResponseValidationError`, `SDKExecutionError`
- `serialize_input_response`, `_coerce_sdk_typed_input`, `_coerce_sdk_params`, `_sdk_runtime_config_with_provider_questions`, `_generate_sdk_task_id`, `_build_synthetic_step_workflow`
- `Engine.run_async`, `RunnerOptions`, `_execute_compiled_workflow`, `_prepare_workspaces`
- `Context.message`, `Context.input_fields`, `Context.input`, `WorkflowInputView`
- `PromptContextView.input`, `_resolve_input_placeholder`, `_resolve_ctx_placeholder`
- `_validate_ctx_prompt_reference`, `_compile_optional_model`

## Checklist mapping
- Milestone 1 runtime input contract refactor: complete via `Context` composite input view, runtime message propagation assertions, and `ctx.input_fields` regression coverage.
- Milestone 2 workflow input validation and rendering: complete via `Workflow.Input.message` compile rejection and runtime placeholder support for `input.message` / `ctx.input.message`.
- Milestone 3 SDK facade and pause loop: complete in `autoloop/sdk.py` with provider resolution, stable SDK task ids, pause/resume loop, handler serialization, result/debug mapping, and sync error normalization.
- Milestone 4 standalone operations and synthetic steps: complete for sync MVP via `Autoloop.llm`, `Autoloop.classify`, `Autoloop.step`, and targeted tests.
- Deferred by design: async SDK entrypoints remain unimplemented; no cleanup/resume/checkpoint public APIs were added.

## Assumptions
- Existing root `autoloop/__init__.py` SDK re-exports were already present in the worktree and did not need a new turn-local edit.
- Runtime provider-question control continues to flow through `RuntimeConfig.full_auto`; the SDK keeps that adaptation local instead of widening runner behavior.

## Preserved invariants
- Runtime persistence still keeps `message`, `workflow_input`, and `workflow_params` separate.
- Omitted runtime messages still fall back to the persisted request snapshot; only explicit `message=None` now stays `None` end-to-end.
- Internal SDK pause/resume reuses one `task_id`, captured `run_id`, stable `message`, stable `workflow_input`, and stable params payload.
- No public resume, checkpoint, event browsing, trace browsing, or cleanup controls were introduced.
- Child workflow runtime compatibility for dict input remains untouched outside the public SDK boundary.

## Intended behavior changes
- Public SDK `run(...)` now enforces exact `Workflow.Input` instances, rejects dict/subclass typed input, maps pause states to SDK-owned result/errors, and exposes debug paths only under `result.debug`.
- `Workflow.Input.message` now fails compilation with the requested definition error.
- `ctx.input.message` now resolves from the runtime message in prompt/runtime template contexts even when no typed input model exists.
- Explicit SDK `message=None` now survives the runner/engine boundary and internal SDK resumes instead of being replaced with the workspace placeholder request text.

## Known non-changes
- No async SDK surface (`arun`, `astep`, `allm`, `aclassify`).
- No artifact cleanup or in-memory artifact snapshots.
- No alternative engine or public lifecycle APIs.

## Expected side effects
- Existing workflows that declared `Workflow.Input.message` now fail validation and must move that data to the top-level SDK/runtime `message`.
- Sync SDK calls inside an active event loop now raise `SDKExecutionError` with async guidance instead of leaking lower-level runtime bridge errors.

## Validation performed
- `./.venv/bin/python -m pytest -q tests/unit/test_sdk_facade.py tests/unit/test_simple_surface.py tests/unit/test_validation.py tests/runtime/test_workspace_and_context.py::test_resume_context_preserves_run_message_and_raw_input_fields tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_bare_input_message_and_fields tests/contract/test_engine_contracts.py::test_runtime_templates_reject_unknown_bare_input_field tests/contract/test_engine_contracts.py::test_runtime_templates_reject_undeclared_ctx_input_message_without_typed_input tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_declared_ctx_input_message_separately_from_request`
- Result: `215 passed`, `14 warnings`.

## Deduplication / centralization
- SDK input coercion, provider-question policy adaptation, task-id generation, result/debug mapping, and synthetic step wrapping were centralized in `autoloop/sdk.py` instead of spreading SDK-only logic across the runner.
- Runtime prompt rendering continues to reuse the existing artifact/template resolvers; only the `ctx.input` view was swapped to the composite input surface.
