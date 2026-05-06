# Implementation Notes

- Task ID: final-standalone-codex-cli-spec-blocked-and-fail-4128a4ed
- Pair: implement
- Phase ID: route-compilation-contract
- Phase Directory Key: route-compilation-contract
- Phase Title: Route Compilation Contract
- Scope: phase-local producer artifact

## Files changed

- `autoloop/core/discovery.py`
- `autoloop/core/compiler.py`
- `tests/unit/test_validation.py`
- `tests/unit/test_simple_surface.py`
- `tests/contract/test_canonical_runtime_contracts.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_runtime_static_graph.py`
- `tests/runtime/test_workspace_and_context.py`
- `tests/unit/test_stdlib_and_extensions.py`

## Symbols touched

- `autoloop.core.discovery._inject_control_routes`
- `autoloop.core.compiler._internal_step_runtime_routes`
- `autoloop.core.compiler._internal_step_runtime_control_routes`

## Checklist mapping

- Plan milestone 1: completed for discovery/compiler route injection and runtime-control classification.
- Plan milestone 2: partially completed for compile/runtime-contract assertions and static-graph/compiled-surface expectations that directly derive from compiled routes.
- Plan milestone 3: deferred in this phase except for packaged-workflow compiled-surface assertions that changed because explicit authored routes are no longer runtime-control.

## Assumptions

- Explicit authored `blocked` / `failed` routes in packaged workflows are intentional opt-ins and must remain present in compiled/provider-visible route tables.
- This phase should not broaden into prompt-only filtering or unrelated runtime status semantics.

## Preserved invariants

- `question` remains the only framework-injected runtime-control route when enabled.
- `question` stays interactive-only in full-auto unless configured otherwise by existing question controls.
- `_compiled_provider_visibility(...)` remains generic for non-`question` routes.

## Intended behavior changes

- Default provider-backed prompt and produce/verify steps no longer compile implicit `blocked` / `failed` routes.
- `runtime_control_routes` now reports only `question` for enabled provider-backed defaults, and `()` when control routes are disabled.
- Explicit authored `blocked` / `failed` routes remain legal but compile as ordinary authored routes with `is_runtime_control=False`.

## Known non-changes

- No prompt-level filtering workaround was added.
- No changes were made to branch-group semantics or runtime status/reporting meanings of `blocked` / `failed`.
- No documentation files were edited in this phase-scoped turn.

## Expected side effects

- Default compiled provider route lists and static-graph/compile-report payloads drop implicit `blocked` / `failed`.
- Packaged workflow snapshots that explicitly include `blocked` / `failed` keep those routes visible, but their runtime-control metadata changes.

## Validation performed

- `python3 -m py_compile autoloop/core/discovery.py autoloop/core/compiler.py tests/unit/test_validation.py tests/unit/test_simple_surface.py tests/contract/test_canonical_runtime_contracts.py tests/runtime/test_runtime_static_graph.py tests/runtime/test_workspace_and_context.py tests/contract/test_engine_contracts.py tests/unit/test_stdlib_and_extensions.py`
- Searched the touched test surface for stale implicit-route expectations after edits.

## Deduplication / centralization

- Route-contract behavior was changed only at discovery/compiler construction points so downstream provider/static-graph surfaces continue deriving from compiled routes without extra filtering branches.
