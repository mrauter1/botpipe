# Test Strategy

- Task ID: below-is-the-revised-sdk-spec-tightened-for-impl-25f82de9
- Pair: test
- Phase ID: input-validation-and-rendering
- Phase Directory Key: input-validation-and-rendering
- Phase Title: Align Validation And Rendering
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- AC-1 / reject `Workflow.Input.message`
  - Covered by `tests/unit/test_validation.py::test_validation_rejects_workflow_input_message_field`.
  - Failure path: compile-time validation raises the spec-defined error instead of allowing the field.
- AC-2 / bare and context input message placeholders validate and render
  - Covered by `tests/unit/test_simple_surface.py::test_simple_workflow_accepts_input_message_prompt_binding`.
  - Covered by `tests/unit/test_simple_surface.py::test_simple_workflow_accepts_ctx_input_message_prompt_binding`.
  - Covered by `tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_ctx_input_message_without_typed_input`.
  - Covered by `tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_declared_ctx_input_message_separately_from_request`.
- Preserved invariant / persisted `workflow_input` excludes `message`
  - Covered by `tests/runtime/test_workspace_and_context.py::test_resume_context_preserves_run_message_and_raw_input_fields`.
  - Checks `ctx.input.message`, raw `ctx.input_fields`, and persisted `run.json` separately across pause/resume.
- Failure path / unknown runtime bare `input.*` placeholder remains an error
  - Covered by `tests/contract/test_engine_contracts.py::test_runtime_templates_reject_unknown_bare_input_field`.

## Edge cases checked

- Message-only context rendering with no typed workflow input model instance.
- Typed input model that also contains a `message` field for runtime rendering separation coverage.
- Resume flow after mutating the task-level request file, to ensure the run-local message snapshot remains authoritative.

## Known gaps

- The phase contract mentions SDK-targeted typed-input coercion around `compiled.input_model`, but no SDK facade/helper exists in-tree yet, so there is no public SDK entrypoint test to add in this phase.
- Runtime execution could not be exercised via `pytest` in this environment because `/usr/bin/python3` does not have `pytest` installed.

## Validation performed

- Updated stale unit expectation in `tests/unit/test_validation.py` to match the now-intentional authoring break and the AC-1 test name referenced in this strategy.
- Corrected the tracked contract/runtime expectations so message-only `{ctx.input.message}` and pause/resume `ctx.input.message` are asserted as success paths instead of preserving the pre-spec typed-only behavior.
- `python3 -m py_compile tests/unit/test_validation.py tests/unit/test_simple_surface.py tests/runtime/test_workspace_and_context.py tests/contract/test_engine_contracts.py`
- Attempted and blocked by environment: `python3 -m pytest tests/unit/test_validation.py -k workflow_input_message` (`No module named pytest`).
- Attempted and blocked by environment: `python3 -m pytest tests/contract/test_engine_contracts.py -k ctx_input_message` (`No module named pytest`).
