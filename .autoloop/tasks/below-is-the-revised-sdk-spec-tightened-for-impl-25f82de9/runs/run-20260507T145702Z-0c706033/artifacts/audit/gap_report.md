# Intent Gap Report

## Original intent considered

- Original request snapshot: complete the remaining follow-up only, not the full earlier SDK/runtime task.
- Requested behaviors:
  - Make every `ctx.*` template path read `ctx.input.message` from the composite runtime input view, including runtime-template rendering and workflow-step child message rendering.
  - Allow directly resolvable strict `ChildWorkflowStep` declarations through `client.step(...)` while still rejecting branch-group, worklist-scoped, and unresolved child-workflow declarations.
  - Add focused regression coverage for message-only and typed-input `ctx.input.message`, successful strict child-step dispatch, unresolved-reference failure, and rerun the focused SDK/runtime slice.

## Clarifications / superseding decisions

- `decisions.txt` block 1 narrowed the runtime fix to the shared `ctx` placeholder resolver so runtime templates and workflow-step child messages inherit the same behavior automatically; it explicitly rejected a bare `{input.message}`-only special case.
- `decisions.txt` block 2 preserved the existing compiler invariant that authored `Workflow.Input` models may not declare `message`; the typed-input regression therefore had to prove `ctx.input.message` through normal typed fields plus the runtime message instead of relaxing that invariant.
- `decisions.txt` blocks 3 and 4 required preserved-behavior coverage for worklist-scoped strict `ChildWorkflowStep` rejection on the same changed SDK preflight path.
- The raw phase log records one intermediate coverage gap (`TST-001`) in the first test-verifier pass, and its closure in test cycle 2. The final audit is against the resulting codebase and final artifacts, not the intermediate incomplete state.

## Implemented behavior

- `autoloop/core/artifacts.py`
  - `PromptContextView.input` now returns `context.input`, the composite runtime view.
  - `_resolve_ctx_placeholder(...)` only raises the missing-input error for `ctx.input.<field>` when the field is not `message`, so `ctx.input.message` resolves from the runtime message even when `input_fields` is absent.
- `autoloop/sdk.py`
  - `_validate_step_declaration_supported(...)` still rejects branch-group and worklist-scoped declarations up front.
  - Strict `ChildWorkflowStep` declarations now only require successful `_ensure_child_workflow_resolvable(...)` and then continue through the existing supported `Step` path instead of a special MVP rejection.
- Focused regression coverage is present in:
  - `tests/unit/test_primitives_and_stores.py`
    - `test_render_runtime_template_resolves_ctx_input_message_without_typed_input`
    - `test_render_runtime_template_resolves_ctx_input_message_from_runtime_message_with_typed_input`
    - `test_render_runtime_template_bare_input_message_uses_runtime_message`
    - `test_render_runtime_template_keeps_bare_input_message_separate_from_ctx_input_message`
  - `tests/contract/test_engine_contracts.py`
    - `test_runtime_templates_resolve_ctx_input_message_without_typed_input`
    - `test_runtime_templates_resolve_ctx_input_message_separately_from_request`
    - `test_workflow_step_message_renders_composite_ctx_input_bindings_before_child_invocation`
  - `tests/unit/test_sdk_facade.py`
    - `test_sdk_step_supports_directly_resolvable_strict_child_workflow_steps`
    - `test_sdk_step_rejects_unresolved_strict_child_workflow_steps`
    - `test_sdk_step_rejects_worklist_scoped_strict_child_workflow_steps`
- Validation evidence:
  - The raw phase log records the final focused slice at `278 passed`.
  - I reran `.venv/bin/python -m pytest -q tests/unit/test_primitives_and_stores.py tests/contract/test_engine_contracts.py tests/unit/test_sdk_facade.py` in the final checkout and it passed with `278 passed in 3.07s`.

## Unresolved gaps

- None material in the final codebase within this run-local scope.

## Differences justified by later clarification or analysis

- Bare `input.*` placeholder behavior was intentionally left unchanged. This is consistent with the request, which targeted `ctx.*` template paths, and with the recorded plan/decision to localize the fix to the shared `ctx` resolver only.
- The follow-up did not add support for authored `Workflow.Input.message` fields. That is explicitly justified by `decisions.txt` block 2 preserving the compiler invariant, while still requiring typed-input coverage that proves `ctx.input.message` comes from the runtime message.
- The first test-verifier pass found missing worklist-scoped rejection coverage, but that difference does not remain unresolved: the second test cycle added `test_sdk_step_rejects_worklist_scoped_strict_child_workflow_steps` and reran the full slice green.

## Recommended next run

- No follow-up implementation run is required for this request. The requested runtime behavior, SDK acceptance boundary, preserved rejection paths, and focused regression slice are all present and validated.
