# Implementation Notes

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: implement
- Phase ID: placeholder-reference-graph
- Phase Directory Key: placeholder-reference-graph
- Phase Title: Placeholder Reference Graph
- Scope: phase-local producer artifact

## Files changed

- `botlane/core/placeholders.py`
- `botlane/core/reference_graph.py`
- `botlane/core/artifacts.py`
- `botlane/core/discovery.py`
- `botlane/core/prompt_validation.py`
- `tests/unit/test_placeholder_refs.py`

## Symbols touched

- Added: `PlaceholderRef`, `parse_placeholders(...)`, `validate_placeholder_ref(...)`, `render_placeholder_ref(...)`, `render_template_with_refs(...)`
- Added: `ReferenceGraph`
- Updated delegation points: `render_runtime_template(...)`, `_reject_ctx_placeholders_in_artifact_template(...)`, `_analyze_simple_prompt_references(...)`, `_validate_simple_prompt_reference(...)`, `analyze_simple_prompt_references(...)`
- Removed duplicate runtime placeholder internals from `botlane/core/artifacts.py` so the new placeholder module is the only runtime implementation.
- Strengthened `test_placeholders_module_does_not_import_context_at_runtime()` to cover plain `import botlane.core.context` in addition to `from ... import ...`.

## Checklist mapping

- Phase objective: added internal placeholder/reference-graph modules and delegated compile-time/runtime placeholder handling through them.
- AC-1: preserved existing validation/rendering behavior in focused placeholder, simple-surface, prompt-context, static-graph, and workspace/context suites.
- Out-of-scope kept out: no placeholder grammar expansion, no public export changes, no workflow-plan/runtime-frame changes.

## Assumptions

- Phase-local behavior preservation is defined by current `WorkflowValidationError` / `WorkflowExecutionError` text and existing placeholder semantics, not by broadening unsupported roots or paths.

## Preserved invariants

- `botlane/core/placeholders.py` does not import `Context` at runtime.
- Prompt and artifact-template placeholder parsing still treat persisted/public metadata as raw strings at boundaries.
- `ctx.*` remains rejected for artifact paths.
- Branch/fan-in placement rules and existing error wording remain unchanged.

## Intended behavior changes

- None. This phase is internal delegation only.

## Known non-changes

- No new placeholder families were added.
- `ReferenceGraph` is introduced as an internal value object only; no engine/runtime consumer was switched to a new graph contract in this phase.
- Static graph / prompt-reference persistence payload shape remains unchanged.

## Expected side effects

- Placeholder parsing is now centralized, reducing regex duplication across compile-time and runtime helper surfaces.
- Branch/fan-in compile-time validation is imported lazily inside the placeholder validator to avoid package-init cycles from `artifacts.py`.
- `botlane/core/artifacts.py` no longer carries a stale second copy of runtime placeholder resolution logic.

## Validation performed

- `./.venv/bin/python -m pytest tests/unit/test_placeholder_refs.py tests/unit/test_primitives_and_stores.py tests/unit/test_simple_surface.py tests/contract/engine/test_prompt_context.py`
- `./.venv/bin/python -m pytest tests/runtime/test_runtime_static_graph.py tests/runtime/test_workspace_and_context.py`
- `./.venv/bin/python -m pytest tests/unit/test_placeholder_refs.py tests/unit/test_primitives_and_stores.py tests/unit/test_simple_surface.py tests/contract/engine/test_prompt_context.py tests/runtime/test_runtime_static_graph.py tests/runtime/test_workspace_and_context.py`
- `python3 -m py_compile botlane/core/placeholders.py botlane/core/reference_graph.py botlane/core/discovery.py botlane/core/artifacts.py botlane/core/prompt_validation.py tests/unit/test_placeholder_refs.py`

## Deduplication / centralization decisions

- Centralized placeholder tokenization and runtime rendering in `botlane/core/placeholders.py`.
- Centralized simple-prompt validation through `validate_placeholder_ref(...)` while leaving public-facing compile/runtime entrypoints unchanged.
- Removed the obsolete runtime placeholder helper copy from `botlane/core/artifacts.py` instead of leaving aliases there.
