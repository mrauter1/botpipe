# Implementation Notes

- Task ID: below-is-the-standalone-implementation-spec-for-b066b1fd
- Pair: implement
- Phase ID: compatibility-bridge-removal
- Phase Directory Key: compatibility-bridge-removal
- Phase Title: Remove Compatibility Bridges
- Scope: phase-local producer artifact

## Files changed

- Production: `autoloop/simple.py`, `core/validation.py`, `runtime/*` import surfaces, `extensions/*` import surfaces, root `__init__.py`, `autoloop_v3/core/__init__.py`
- Deleted: `core/_compat.py`
- Tests: maintained contract/runtime/unit import surfaces plus `tests/strictness/test_no_compat.py` and `tests/unit/test_simple_surface.py`

## Symbols touched

- `autoloop.simple` canonical import block
- `core.validation._is_base_workflow_class`
- `core.validation._inherits_supported_workflow_base`
- `autoloop_v3.core` failure shim
- strictness scan helpers for removed compatibility imports

## Checklist mapping

- AC-1: completed
  Canonicalized maintained production and non-strictness test/fixture imports to `core...` or `autoloop...`; removed `core/_compat.py`; added import-statement scans for `autoloop_v3.core*` and `core._compat`.
- AC-2: completed in code
  `autoloop_v3.core` now fails intentionally via `ModuleNotFoundError`; canonical `core` and `autoloop` imports remain the maintained path.

## Assumptions

- The root-level `core/`, `runtime/`, `extensions/`, and `tests/` trees are the authoritative active codebase for this phase; deleted `autoloop_v3/...` source files are legacy residue.

## Preserved invariants

- No public API naming changes beyond removing the deprecated core bridge path.
- `autoloop_v3.runtime` and other non-core namespace surfaces were left alone in this phase.
- No hook, state, telemetry, or required-write behavior was changed.

## Intended behavior changes

- Direct imports of `autoloop_v3.core` and `autoloop_v3.core._compat` now fail intentionally.
- Workflow base detection in `core.validation` recognizes only canonical `core.Workflow` and `autoloop.simple.Workflow`.

## Known non-changes

- Did not rename or re-export public symbols beyond existing phase scope.
- Did not migrate remaining `autoloop_v3.runtime` / `autoloop_v3.extensions` / `autoloop_v3.stdlib` imports because this phase targets the removed core bridge only.

## Expected side effects

- Strictness coverage now treats legacy core imports as forbidden across maintained Python sources, including generated source snippets embedded in tests.
- `python3 -m py_compile` refreshed tracked `__pycache__/*.pyc` files in this worktree during syntax validation.

## Validation performed

- `rg -n "from autoloop_v3\\.core|import autoloop_v3\\.core|from core\\._compat|import core\\._compat|bridge_core_package" autoloop core extensions runtime workflows tests/contract tests/fixtures tests/runtime tests/unit -S`
  Result: no matches
- `python3 -m py_compile ...` across all edited production and test files
  Result: passed
- `python3 -m pytest tests/strictness/test_no_compat.py tests/unit/test_simple_surface.py -q`
  Blocked: environment lacks `pytest` and `pydantic`

## Deduplication / centralization decisions

- Removed the duplicated installed-package vs repo-root fallback pattern for core imports in the touched production modules; all now use one canonical `core...` path.
