# Implementation Notes

- Task ID: standalone-implementation-spec-ctx-prompt-bindin-edf74165
- Pair: implement
- Phase ID: finish-ctx-request-input-separation
- Phase Directory Key: finish-ctx-request-input-separation
- Phase Title: Finish Ctx Request And Input Separation
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/context.py`
- `autoloop/core/artifacts.py`
- `autoloop/core/discovery.py`
- `autoloop/core/compiler.py`
- `autoloop/core/engine.py`
- `autoloop/core/branch_groups/context.py`
- `autoloop/runtime/runner.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/unit/test_branch_group_context_sessions.py`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_validation.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_workspace_and_context.py`
- `../runs/run-20260507T132940Z-5d96f5de/decisions.txt`

## Symbols touched
- `WorkflowInputView`
- `Context.input`
- `_resolve_input_placeholder`
- `_resolve_ctx_placeholder`
- `_validate_ctx_prompt_reference`
- `_compile_optional_model`
- `Engine.run_async`
- `create_branch_context`
- `_execute_compiled_workflow`

## Checklist mapping
- Plan 1: Removed synthetic `ctx.input.message` behavior from validation/runtime surfaces; direct Python `ctx.input.message` and `ctx.input.model_dump()` now follow declared `Input` fields only.
- Plan 2: Restored file-backed root/clone `ctx.message` semantics by keeping `_DEFAULT_MESSAGE` through runner, engine root contexts, and branch/fan-in clones.
- Plan 3: Rebased regression coverage for undeclared vs declared `ctx.input.message`, `{ctx.message}` prompt/message rendering, resume snapshot authority, unreadable snapshot failure, and child input/request separation.
- Reviewer follow-up: corrected stale unit expectations so undeclared `ctx.input.message` is rejected while explicit `Input.message` remains accepted.

## Assumptions
- Allowing `Workflow.Input.message` is required to satisfy the requested “valid only when explicitly declared” contract, so the previous compiler ban was part of the drift and not a preserved invariant.

## Preserved invariants
- `ctx.message` and `ctx.request.text` remain the built-in request-text bindings.
- Artifact-path rejection for `ctx.*` remains unchanged.
- `Context(message=...)` still works as an explicit synthetic override outside runner/engine root construction.

## Intended behavior changes
- `ctx.input.message` is no longer a built-in request alias; it now resolves only when `Input.message` is declared.
- Direct Python `ctx.input.message` / `ctx.input.model_dump()` no longer include request text unless `Input.message` is declared.
- Root engine contexts, resumed contexts, and branch/fan-in clones now keep request-file authority instead of caching request text.

## Known non-changes
- Bare compatibility placeholders such as `{input.topic}` remain supported.
- Bare `{input.message}` remains supported as an isolated compatibility shim.

## Expected side effects
- Workflows/tests that relied on undeclared `ctx.input.message` now need `{ctx.message}` instead.
- Workflows may now intentionally declare `Input.message` when they need typed structured input under that field name.

## Validation performed
- `./.venv/bin/python -m pytest tests/unit/test_primitives_and_stores.py tests/unit/test_branch_group_context_sessions.py tests/unit/test_simple_surface.py tests/unit/test_validation.py`
- `./.venv/bin/python -m pytest tests/contract/test_engine_contracts.py -k "ctx_prompt_bindings_render_in_provider_and_operation_prompts or runtime_templates_resolve_bare_input_message_and_fields or runtime_templates_reject_undeclared_ctx_input_message or runtime_templates_resolve_declared_ctx_input_message_separately_from_request or engine_context_message_raises_when_run_snapshot_is_removed_after_context_construction or ctx_runtime_prompt_docs_describe_preferred_bindings_and_snapshot_semantics or workflow_step_message_can_forward_ctx_message_into_child_request_snapshot or workflow_step_message_renders_ctx_bindings_before_child_invocation"`
- `./.venv/bin/python -m pytest tests/runtime/test_workspace_and_context.py -k "resume_context_message_uses_run_local_request_snapshot_not_mutated_task_request or resume_context_preserves_run_message_and_raw_input_fields"`

## Deduplication / centralization decisions
- Kept the legacy bare `{input.message}` fallback isolated in `_resolve_input_placeholder` rather than leaking request-text aliasing back into `WorkflowInputView` or `ctx.*`.
