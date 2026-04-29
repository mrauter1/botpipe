# Test Strategy

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: test
- Phase ID: public-surface-cleanup
- Phase Directory Key: public-surface-cleanup
- Phase Title: Canonical Public Surface
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- AC-1 canonical root import surface:
  - `tests/unit/test_simple_surface.py`
  - `tests/strictness/test_no_compat.py`
  - Covers canonical `autoloop.__all__`, successful canonical imports, and failure of removed public symbols.
- AC-2 canonical simple declaration surface:
  - `tests/unit/test_simple_surface.py`
  - Covers canonical `step` / `produce_verify_step` / `python_step` signatures, rejection of legacy keywords (`out`, `outputs`, `do`, `review`, `review_writes`), and BaseModel-backed `State` / `Params` / step `state`.
- Repo consumer regression guard for the renamed pair-step API:
  - `tests/runtime/test_workflow_integration_parity.py::test_all_repo_workflow_packages_resolve_and_compile_under_canonical_simple_surface`
  - Covers the reviewer-found failure mode where checked-in workflows still instantiated `produce_verify_step(..., writes=...)`.

## Preserved invariants checked

- Discovered repo workflow packages still resolve by canonical package name under explicit `REPO_ROOT`.
- Every checked-in repo workflow package compiles through the same runtime loader + compiler path used by execution.
- The public-surface cleanup does not reintroduce removed aliases to make repo workflows compile.

## Edge cases and failure paths

- Legacy simple keywords fail fast with `TypeError`.
- Simple workflows using `Parameters` or non-BaseModel step `state` fail validation.
- The compile sweep test fails on the first future workflow package that drifts back to a banned simple-surface signature.

## Flake risks / stabilization

- Workflow module caching can leak across tests; stabilized with `_clear_workflow_modules()` and `importlib.invalidate_caches()`.
- The repo-wide compile sweep emits known Pydantic warnings from existing workflow contracts; the test asserts compilation success and does not depend on warning ordering or wording.

## Known gaps

- This test pass does not add new coverage for the remaining non-blocking authoring-doc vocabulary drift (`Parameters`, `route_infos`, `route_required_outputs`).
