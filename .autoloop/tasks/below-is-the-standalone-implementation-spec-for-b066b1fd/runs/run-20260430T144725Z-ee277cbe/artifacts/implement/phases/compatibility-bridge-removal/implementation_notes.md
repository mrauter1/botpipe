# Implementation Notes

- Task ID: below-is-the-standalone-implementation-spec-for-b066b1fd
- Pair: implement
- Phase ID: compatibility-bridge-removal
- Phase Directory Key: compatibility-bridge-removal
- Phase Title: Remove Compatibility Bridges
- Scope: phase-local producer artifact

## Files changed

- Production: `autoloop/simple.py`, `core/validation.py`, `core/workflow_capabilities.py`, `runtime/*` import surfaces, `extensions/*` import surfaces, `autoloop_optimizer/*`, `workflows/*` optimizer consumers, root `__init__.py`, `autoloop_v3/core/__init__.py`
- Deleted: `core/_compat.py`
- Tests: maintained runtime/unit/strictness import surfaces, embedded workflow fixture snippets, `tests/strictness/test_no_compat.py`, `tests/unit/test_simple_surface.py`, and `tests/unit/test_stdlib_and_extensions.py`

## Symbols touched

- `autoloop.simple` canonical import block
- `core.validation._is_base_workflow_class`
- `core.validation._inherits_supported_workflow_base`
- `core.workflow_capabilities._inspect_catalog_entry`
- `core.workflow_capabilities._resolve_reference`
- `autoloop_optimizer` absolute-import seams
- `autoloop_v3.core` failure shim
- strictness scan helpers for removed compatibility imports

## Checklist mapping

- Milestone 1 / AC-1: completed
  Canonicalized maintained production and test/fixture imports off deleted `autoloop_v3.*` namespaces to root `core`, `runtime`, `extensions`, `stdlib`, `workflows`, and `autoloop_optimizer`; removed `core/_compat.py`; added import-statement scans for forbidden compatibility paths.
- Milestone 1 / AC-2: completed in code
  `autoloop_v3.core` now fails intentionally via `ModuleNotFoundError`; canonical root packages remain the maintained import path across the active regression surface.

## Assumptions

- The root-level `core/`, `runtime/`, `extensions/`, `stdlib/`, `workflows/`, `autoloop_optimizer/`, and `tests/` trees are the authoritative active codebase for this phase; deleted `autoloop_v3/...` source files are legacy residue.

## Preserved invariants

- No public API naming changes beyond removing deprecated compatibility import paths.
- No hook, state, telemetry, or required-write behavior was changed.

## Intended behavior changes

- Direct imports of `autoloop_v3.core` and `autoloop_v3.core._compat` now fail intentionally.
- Workflow base detection in `core.validation` recognizes only canonical `core.Workflow` and `autoloop.simple.Workflow`.
- Maintained workflows and tests no longer rely on deleted `autoloop_v3.runtime`, `autoloop_v3.extensions`, `autoloop_v3.stdlib`, `autoloop_v3.workflows`, or `autoloop_v3.autoloop_optimizer` namespaces.
- The canonical optimizer helper package is `autoloop_optimizer`, with absolute imports to the root `core`, `runtime`, and `stdlib` packages.

## Known non-changes

- Did not rename or re-export public symbols beyond existing phase scope.
- Did not restore any deleted `autoloop_v3.*` package trees beyond the intentional `autoloop_v3.core` failure shim.

## Expected side effects

- Strictness coverage now treats legacy compatibility imports as forbidden across maintained Python sources, while keeping one intentional failed-import assertion for `autoloop_v3.core`.
- `python3 -m py_compile` refreshed tracked `__pycache__/*.pyc` files in this worktree during syntax validation.

## Validation performed

- `rg -n "autoloop_v3\\.(core|runtime|extensions|stdlib|workflows|autoloop_optimizer)|core\\._compat|bridge_core_package" autoloop core runtime extensions stdlib workflows tests/fixtures tests/runtime tests/unit tests/contract tests/strictness -S`
  Result: only the intentional strictness failure assertion for `autoloop_v3.core`
- `rg -n "from \\.\\.|import \\.\\." autoloop_optimizer -S`
  Result: no matches
- `python3 -m py_compile core/workflow_capabilities.py $(find autoloop_optimizer workflows tests/runtime tests/unit tests/strictness -name '*.py' ...)`
  Result: passed
- `python3 -m pytest tests/strictness/test_no_compat.py tests/unit/test_simple_surface.py -q`
  Blocked: environment lacks `pytest` and `pydantic`

## Deduplication / centralization decisions

- Removed the duplicated installed-package vs repo-root fallback pattern for touched production modules; active code now uses one canonical root-package path per surface (`core`, `runtime`, `extensions`, `stdlib`, `workflows`, `autoloop_optimizer`).
