# Test Strategy

- Task ID: below-is-the-revised-sdk-spec-tightened-for-impl-25f82de9
- Pair: test
- Phase ID: close-remaining-sdk-runtime-gaps
- Phase Directory Key: close-remaining-sdk-runtime-gaps
- Phase Title: Close Remaining SDK/Runtime Contract Gaps
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- AC-1 runtime template rendering:
  - `tests/unit/test_primitives_and_stores.py::test_render_runtime_template_resolves_ctx_input_message_without_typed_input`
  - `tests/unit/test_primitives_and_stores.py::test_render_runtime_template_resolves_ctx_input_message_from_runtime_message_with_typed_input`
  - `tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_ctx_input_message_without_typed_input`
  - `tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_ctx_input_message_separately_from_request`
- Preserved bare placeholder behavior:
  - `tests/unit/test_primitives_and_stores.py::test_render_runtime_template_bare_input_message_uses_runtime_message`
  - `tests/unit/test_primitives_and_stores.py::test_render_runtime_template_keeps_bare_input_message_separate_from_ctx_input_message`
  - `tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_bare_input_message_and_fields`
- AC-2 workflow-step child message rendering:
  - `tests/contract/test_engine_contracts.py::test_workflow_step_message_renders_composite_ctx_input_bindings_before_child_invocation`
- AC-3 SDK strict child-workflow dispatch:
  - `tests/unit/test_sdk_facade.py::test_sdk_step_supports_directly_resolvable_strict_child_workflow_steps`
  - `tests/unit/test_sdk_facade.py::test_sdk_step_rejects_unresolved_strict_child_workflow_steps`
  - `tests/unit/test_sdk_facade.py::test_sdk_step_rejects_worklist_scoped_strict_child_workflow_steps`

## Preserved invariants checked

- `ctx.input.<field>` still reads typed fields while `ctx.input.message` follows the runtime message.
- Bare `input.message` compatibility remains unchanged and distinct from `ctx.input.message`.
- Branch-group, worklist-scoped, and unresolved child-workflow declarations remain rejected outside the new strict resolvable success case.
- Workflow-step message rendering still uses the shared runtime template path instead of a second bespoke code path.

## Edge cases and failure paths

- No-typed-input `ctx.input.message` rendering.
- Typed input present with a separate runtime message and typed fields.
- Unresolved strict child-workflow reference at the SDK boundary.
- Worklist-scoped strict child-workflow declaration rejection at the SDK boundary.

## Flake-risk review and stabilization

- Coverage is deterministic: all tests use in-memory stores, local temporary workspaces, direct child invokers or fake providers, and explicit assertions on rendered strings / SDK exceptions.
- No timing, network, or ordering dependencies were introduced.

## Validation slice

- `.venv/bin/python -m pytest -q tests/unit/test_primitives_and_stores.py tests/contract/test_engine_contracts.py tests/unit/test_sdk_facade.py`
- Result: `278 passed`

## Known gaps

- No additional gaps identified within this phase scope; broader placeholder-engine redesign remains intentionally out of scope.
