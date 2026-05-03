# Implementation Notes

- Task ID: standalone-remaining-delta-implementation-spec-g-e919a184
- Pair: implement
- Phase ID: public-contract-cleanup
- Phase Directory Key: public-contract-cleanup
- Phase Title: Public Contract Cleanup
- Scope: phase-local producer artifact

## Files changed

- `autoloop/core/context.py`
- `autoloop/core/worklists.py`
- `autoloop/core/steps.py`
- `autoloop/core/discovery.py`
- `autoloop/core/compiler.py`
- `autoloop/core/hook_validation.py`
- `autoloop/core/state_validation.py`
- `autoloop/core/topology.py`
- `autoloop/core/engine.py`
- `autoloop/core/engine_collaborators.py`
- `autoloop/stdlib/control.py`
- `docs/authoring.md`
- `docs/workflows/workflow_idea_to_workflow_package.md`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/workflow_contract_helpers.py`
- `tests/fixtures/toy_runtime_workflow.py`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_validation.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/unit/test_stdlib_and_extensions.py`
- `tests/test_architecture_baseline_docs.py`

## Symbols touched

- `Context`, `_ContextRuntime`, `context_runtime`, `WorklistRuntimeView`
- `ProduceVerifyStep`
- `CompiledStep`, `CompiledWorkflow`, `_compile_steps`, `_compile_system_handler`
- `validate_handlers`, `validate_step_hooks`, `has_start_hook`, `outcome_middleware_name`
- `event_on_outcome_tags`

## Checklist mapping

- Public contract cleanup: completed for author-facing `Context` mutators/cache setters, removal of legacy class-level handler compilation/validation, pair-step public keyword vocabulary, and public validation/error wording around `python_step`.
- Strictness/simple-surface coverage: completed with maintained unit/strictness/contract test migration to explicit step-local hooks and `python_step` handlers, plus docs/stdlib helper updates to final hook vocabulary.
- Prompt placeholder validation: no code change; existing discovery validation already failed unknown/ambiguous placeholders at compile/preflight.

## Assumptions

- Removing legacy pair-step public constructor keywords (`review_session`, `before_do`, `after_do`, `before_review`, `after_review`) is in-scope for this public-contract slice because repo workflows do not depend on them outside tests.
- The remaining large contract/runtime refactors in later phases can rely on explicit step hooks and explicit `python_step` handlers only; no class-handler compatibility shim remains in the compiler path.
- Maintained tests that previously used class-level handlers now need explicit helper functions attached to step declarations; negative tests that still assert orphan-handler failures keep only the intentionally orphaned alias methods.

## Preserved invariants

- Hook/worklist runtime behavior is unchanged apart from the public `Context` method surface and the intentional rejection of legacy class-level handler authoring.
- Worklist helper mutations still update selection state, scoped state sync, and emitted worklist trace events.
- Existing simple-workflow compile behavior and placeholder inference/validation remain intact.

## Intended behavior changes

- Hook-facing `Context` no longer exposes underscore mutator/cache methods like `_set_state`, `_set_route`, `_set_selection`, or `_cache_worklist_items`.
- Hook-facing `Context` also no longer exposes `ctx._runtime`; internal runtime code now resolves mutation helpers through `context_runtime(ctx)`.
- Core pair-step public keywords now use final producer/verifier naming only.
- Workflow-level `on_start`, `on_outcome`, and step-level `on_<step>` class handlers are rejected instead of compiled.
- `python_step` no longer falls back to class-level `on_<step>` methods and requires an explicit one-argument handler.
- Validation messages use `python_step` wording for retry-policy / expected-output contract failures.
- Public docs/examples now describe explicit `before(ctx)`, `after(ctx)`, `Route.to(..., on_taken=...)`, and explicit `python_step` handlers instead of legacy `on_start` / `on_<step>` forms.
- `event_on_outcome_tags(...)` now returns a `hook(ctx)` helper that reads `ctx.outcome` instead of the removed `(state, outcome)` callable shape.

## Known non-changes

- No saved-run resume/cache behavior changes.
- No provider contract builder extraction.
- No saved-run resume mismatch warning changes, route-finalization dataclass migration, or broader provider retry/history refactors beyond the public-contract test surfaces touched here.

## Expected side effects

- Internal helpers/tests that reached context underscore mutators must use `context_runtime(ctx)`.
- Core pair-step call sites using removed do/review keyword names now fail fast with `TypeError`.
- Legacy workflow classes that still declare `on_start`, `on_outcome`, or `on_<step>` now fail validation immediately.
- Maintained docs, stdlib control helpers, and contract/validation fixtures now model the final explicit hook surface, so stale public examples no longer fail simply because they teach removed APIs.

## Validation performed

- `./.venv/bin/python -m py_compile autoloop/core/context.py autoloop/core/worklists.py autoloop/core/compiler.py autoloop/core/hook_validation.py autoloop/core/discovery.py autoloop/core/lowering.py autoloop/core/engine.py autoloop/core/engine_collaborators.py tests/runtime/workflow_contract_helpers.py tests/unit/test_primitives_and_stores.py tests/unit/test_simple_surface.py tests/unit/test_validation.py tests/fixtures/toy_runtime_workflow.py`
- `./.venv/bin/pytest tests/unit/test_primitives_and_stores.py::test_public_context_hides_runtime_mutators tests/unit/test_primitives_and_stores.py::test_worklist_runtime_view_updates_selection_emits_events_and_returns_exhaustion_control tests/unit/test_simple_surface.py::test_simple_workflow_rejects_legacy_class_level_handler_methods tests/unit/test_simple_surface.py::test_runtime_built_in_step_state_is_available_on_core_steps tests/unit/test_validation.py::test_validation_accepts_direct_system_step_handler_without_on_step_method tests/unit/test_validation.py::test_validation_rejects_legacy_on_start_handler_even_when_step_is_named_start tests/unit/test_validation.py::test_validation_rejects_legacy_on_outcome_handler_even_when_step_is_named_outcome tests/unit/test_validation.py::test_validation_rejects_legacy_class_level_step_handler_methods tests/unit/test_validation.py::test_validation_rejects_legacy_pair_handler_methods tests/unit/test_validation.py::test_validation_rejects_multi_argument_python_step_handler tests/unit/test_validation.py::test_validation_does_not_infer_after_hook_routes_from_source tests/unit/test_validation.py::test_validation_rejects_multi_argument_after_hook_signature tests/unit/test_validation.py::test_validation_does_not_infer_after_producer_redirects_from_source tests/unit/test_validation.py::test_validation_rejects_multi_argument_after_producer_hook_signature tests/unit/test_validation.py::test_validation_rejects_static_on_start_signature -q`
- `./.venv/bin/pytest tests/strictness/test_no_compat.py -q`
- `./.venv/bin/python -m py_compile autoloop/stdlib/control.py tests/contract/test_engine_contracts.py tests/unit/test_validation.py tests/unit/test_primitives_and_stores.py tests/unit/test_stdlib_and_extensions.py`
- `./.venv/bin/pytest tests/contract/test_engine_contracts.py tests/unit/test_validation.py tests/unit/test_simple_surface.py tests/unit/test_primitives_and_stores.py tests/unit/test_stdlib_and_extensions.py::test_control_helpers_merge_routes_and_build_outcome_passthrough tests/strictness/test_no_compat.py -q`

## Deduplication / centralization

- Consolidated context mutation, worklist cache access, selection sync, and worklist event emission into `_ContextRuntime` plus the internal `context_runtime(ctx)` lookup instead of leaving those mutators on the author-facing `Context` surface.
