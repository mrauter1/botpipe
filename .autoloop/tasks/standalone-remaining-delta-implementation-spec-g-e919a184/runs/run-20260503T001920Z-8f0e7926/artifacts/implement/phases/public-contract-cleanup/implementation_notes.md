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
- `tests/runtime/workflow_contract_helpers.py`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_validation.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/test_architecture_baseline_docs.py`

## Symbols touched

- `Context`, `_ContextRuntime`, `WorklistRuntimeView`
- `ProduceVerifyStep`
- `_compile_steps`, `_compile_system_handler`
- `validate_step_hooks`, `validate_sessions`, `validate_worklists`, `validate_control_contracts`

## Checklist mapping

- Public contract cleanup: completed for author-facing `Context` mutators/cache setters, pair-step public keyword vocabulary, and public validation/error wording around `python_step`.
- Strictness/simple-surface coverage: completed with focused unit/strictness test updates for hidden context mutators and removed pair-step legacy keywords.
- Prompt placeholder validation: no code change; existing discovery validation already failed unknown/ambiguous placeholders at compile/preflight.

## Assumptions

- Removing legacy pair-step public constructor keywords (`review_session`, `before_do`, `after_do`, `before_review`, `after_review`) is in-scope for this public-contract slice because repo workflows do not depend on them outside tests.
- Full removal of legacy strict core class-handler execution paths remains outside this patch slice; this turn avoids widening into the larger engine/runtime compatibility break set.

## Preserved invariants

- Hook/worklist runtime behavior is unchanged apart from the public `Context` method surface.
- Worklist helper mutations still update selection state, scoped state sync, and emitted worklist trace events.
- Existing simple-workflow compile behavior and placeholder inference/validation remain intact.

## Intended behavior changes

- Hook-facing `Context` no longer exposes underscore mutator/cache methods like `_set_state`, `_set_route`, `_set_selection`, or `_cache_worklist_items`.
- Internal runtime code now mutates context/worklist state through `context._runtime`.
- Core pair-step public keywords now use final producer/verifier naming only.
- Validation messages use `python_step` wording for retry-policy / expected-output contract failures.

## Known non-changes

- No saved-run resume/cache behavior changes.
- No provider contract builder extraction.
- No broad removal of legacy strict-core `on_<step>` / `on_start` / `on_outcome` execution paths in this turn.

## Expected side effects

- Internal helpers/tests that reached context underscore mutators must use `context._runtime`.
- Core pair-step call sites using removed do/review keyword names now fail fast with `TypeError`.

## Validation performed

- `./.venv/bin/pytest tests/unit/test_simple_surface.py tests/unit/test_validation.py tests/unit/test_primitives_and_stores.py -q`
- `./.venv/bin/pytest tests/strictness/test_no_compat.py -q`

## Deduplication / centralization

- Consolidated context mutation, worklist cache access, selection sync, and worklist event emission into `_ContextRuntime` instead of leaving those mutators on the author-facing `Context` surface.
