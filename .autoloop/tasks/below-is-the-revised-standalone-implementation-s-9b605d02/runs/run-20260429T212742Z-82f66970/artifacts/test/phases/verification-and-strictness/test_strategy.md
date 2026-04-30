# Test Strategy

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: test
- Phase ID: verification-and-strictness
- Phase Directory Key: verification-and-strictness
- Phase Title: Verification Gate
- Scope: phase-local producer artifact

## Coverage map

- AC-1 strictness surface:
  - `tests/strictness/test_no_compat.py`
  - Covers banned public imports and removed emitted payload keys on the maintained canonical authoring/docs/workflow surface.
- AC-2 canonical contract surface:
  - `tests/contract/test_canonical_runtime_contracts.py`
  - Covers `FINISH`, `produce_verify`, `route_required_writes`, split producer/verifier writable artifacts, and absence of removed provider fields.
- AC-2 topology/doc/runtime validation:
  - `tests/test_architecture_baseline_docs.py`
  - `tests/unit/test_simple_surface.py`
  - `tests/runtime/test_runtime_static_graph.py`
  - Covers canonical docs/examples, compiled simple-surface defaults, and static graph/topology vocabulary.
- AC-2 workflow/package parity and resume/session artifacts:
  - `tests/runtime/test_workflow_integration_parity.py`
  - Covers copied workflow package discovery/compile/run, canonical session file layout, clarification resume persistence, blocked-status mapping, and repo-root-free copied-package execution.

## Edge cases and failure paths

- Strictness scan excludes internal compatibility modules/tests so the gate matches the recorded canonical-surface scope instead of normalizing out-of-phase internals.
- Copied workflow execution is exercised with the repo root removed from `sys.path` to catch regressions in top-level `core` / `extensions` / `runtime` imports.
- Resume path coverage checks canonical placeholder-vs-bound session payloads and rejects legacy continuation-key leakage.

## Stabilization

- All provider interactions use `ScriptedLLMProvider`.
- Filesystem assertions operate in per-test temporary directories.
- No network, timing, or nondeterministic ordering dependencies are introduced.

## Known gaps

- The broader low-level compatibility suites remain out of phase by design and are not re-baselined here.
