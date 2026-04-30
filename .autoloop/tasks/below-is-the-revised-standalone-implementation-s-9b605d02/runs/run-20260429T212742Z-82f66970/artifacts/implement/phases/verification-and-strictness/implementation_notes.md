# Implementation Notes

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: implement
- Phase ID: verification-and-strictness
- Phase Directory Key: verification-and-strictness
- Phase Title: Verification Gate
- Scope: phase-local producer artifact

## Files changed

- `extensions/session_paths.py`
- `extensions/tracing.py`
- `extensions/git/declaration.py`
- `extensions/git/filters.py`
- `extensions/git/policy.py`
- `extensions/git/runtime.py`
- `runtime/loader.py`
- `runtime/runner.py`
- `runtime/static_graph.py`
- `runtime/tracing.py`
- `runtime/git_tracking.py`
- `runtime/observability.py`
- `runtime/prompts.py`
- `runtime/stores/filesystem.py`
- `cleanup.md`
- `Workflow_Instructions.md`
- `docs/authoring.md`
- `workflows/*/prompts/README.md` for canonical required-writes vocabulary
- `tests/strictness/test_no_compat.py`
- `tests/test_architecture_baseline_docs.py`
- `tests/unit/test_simple_surface.py`
- `tests/contract/test_canonical_runtime_contracts.py`
- `tests/runtime/test_workflow_integration_parity.py`

## Symbols touched

- Repo-root package import seams for `extensions.*` and `runtime.*`
- Strictness scan roots and canonical payload checks
- Canonical doc vocabulary: `produce_verify_step`, `required_writes`, `global` session slot
- Canonical runtime contract assertions for provider calls and repo workflow parity

## Checklist mapping

- Plan milestone 5 / AC-1: added public-surface strictness scan and emitted-payload assertions in `tests/strictness/test_no_compat.py`
- Plan milestone 5 / AC-2: added canonical engine/provider contract coverage in `tests/contract/test_canonical_runtime_contracts.py`
- Plan milestone 5 / AC-2: updated docs, doc tests, simple-surface tests, and repo workflow parity checks to the canonical contract
- No checklist items intentionally deferred within this phase; the broader legacy low-level compatibility suite remains out-of-phase by design

## Assumptions

- Verification gate should prove the canonical public/runtime surface, not preserve every legacy assertion in the low-level compatibility harness
- Repo-authored workflows that import top-level `core` / `extensions` / `runtime` must still execute from copied workflow packages

## Preserved invariants

- Public `autoloop` exports remain canonical-only
- Persisted legacy session payload readers remain untouched; only repo-root import fallbacks and verification expectations changed here
- Topology/static-graph payloads continue to emit canonical `FINISH`, `produce_verify`, and `required_writes`

## Intended behavior changes

- Public docs/readmes no longer describe removed keys such as `route_infos`, `route_required_outputs`, `do_review_step`, or the `default` session slot
- Repo-root `runtime` and `extensions` packages can now be imported directly by copied workflow packages without relative-import failures
- `autoloop_v1` parity assertions now match the canonical session file layout: placeholder session metadata in `sessions/<name>.json` and concrete bindings in `sessions/<name>_session.json` / scoped session files

## Known non-changes

- Internal low-level compatibility scaffolding in `core/*` still exists for out-of-phase consumers
- The legacy compatibility-heavy suites (`tests/contract/test_engine_contracts.py`, `tests/runtime/test_compatibility_runtime.py`) were not migrated in this verification phase

## Expected side effects

- Top-level imports of `runtime.*` and `extensions.*` now succeed in more contexts, especially copied workflow package execution
- Canonical strictness scan no longer treats internal compatibility modules/tests as the cleanup acceptance surface

## Validation performed

- `./.venv/bin/python -m pytest -q tests/strictness/test_no_compat.py tests/test_architecture_baseline_docs.py tests/unit/test_simple_surface.py tests/unit/test_provider_boundary_core.py tests/contract/test_canonical_runtime_contracts.py tests/runtime/test_runtime_static_graph.py tests/runtime/test_workflow_reference_resolution.py tests/runtime/test_workflow_integration_parity.py tests/runtime/test_provider_backends.py`
  - Result: `111 passed`
  - Warnings: existing Pydantic `schema` field-name warnings from `workflows/workflow_run_traces_to_optimization_candidates/contracts.py`

## Deduplication / centralization

- Reused the same installed-package-or-repo-root import fallback pattern already present in `autoloop.simple` across repo-root `extensions` and `runtime` modules instead of adding workflow-specific shims
