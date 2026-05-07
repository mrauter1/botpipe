# Implementation Notes

- Task ID: below-is-the-revised-sdk-spec-tightened-for-impl-25f82de9
- Pair: implement
- Phase ID: close-remaining-sdk-runtime-gaps
- Phase Directory Key: close-remaining-sdk-runtime-gaps
- Phase Title: Close Remaining SDK/Runtime Contract Gaps
- Scope: phase-local producer artifact

## Files changed

- `autoloop/core/artifacts.py`
- `autoloop/sdk.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/contract/test_engine_contracts.py`
- `tests/unit/test_sdk_facade.py`
- `runs/run-20260507T145702Z-0c706033/decisions.txt`

## Symbols touched

- `PromptContextView.input`
- `_resolve_ctx_placeholder(...)`
- `_validate_step_declaration_supported(...)`

## Checklist mapping

- Plan item 1: completed via composite `ctx.input` lookup in `autoloop/core/artifacts.py`.
- Plan item 2: completed via strict `ChildWorkflowStep` acceptance after existing resolution preflight in `autoloop/sdk.py`.
- Plan item 3: completed via focused regressions in the three requested test files and full three-file slice rerun.

## Assumptions

- The accepted follow-up only changes `ctx.*` template resolution; bare `input.*` compatibility remains intentionally unchanged.
- Strict child-workflow support is limited to already-resolvable, unscoped declarations and should not introduce a new execution path.

## Preserved invariants

- Authored workflow `Input` models still may not declare a `message` field.
- Branch-group, worklist-scoped, and unresolved child-workflow declarations still fail at the SDK boundary.
- Workflow-step message rendering still goes through the shared `render_runtime_template(...)` path.

## Intended behavior changes

- `ctx.input.message` now resolves from the runtime message through the composite input view even when `input_fields` is absent.
- When typed input exists, `ctx.input.message` still resolves from the runtime message while `ctx.input.<field>` continues to read typed fields.
- `client.step(...)` now accepts directly resolvable strict `ChildWorkflowStep` declarations and executes them through the existing synthetic one-step workflow path.

## Known non-changes

- Bare `input.message` / `input.<field>` placeholder behavior was not modified.
- `WorkflowInputView.model_dump(...)` was not changed as part of this scoped template-resolution follow-up.

## Expected side effects

- Runtime prompt rendering and workflow-step child message rendering now share the corrected `ctx.input.message` behavior without extra branching.
- Contract tests that use parametrized local workflow classes now avoid compiler-cache collisions by giving each case a unique qualname.

## Validation performed

- `.venv/bin/python -m pytest -q tests/unit/test_primitives_and_stores.py -k 'ctx_input_message or bare_input_message'`
- `.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py -k 'ctx_input_message or composite_ctx_input_bindings_before_child_invocation'`
- `.venv/bin/python -m pytest -q tests/unit/test_sdk_facade.py -k 'strict_child_workflow or core_python_step_instances or synthetic_simple_operation_workflow'`
- `.venv/bin/python -m pytest -q tests/unit/test_primitives_and_stores.py tests/contract/test_engine_contracts.py tests/unit/test_sdk_facade.py`

## Deduplication / centralization

- The runtime fix stays centralized in the shared `ctx` placeholder resolver so artifact-style runtime templates and workflow-step child messages inherit the same behavior automatically.
