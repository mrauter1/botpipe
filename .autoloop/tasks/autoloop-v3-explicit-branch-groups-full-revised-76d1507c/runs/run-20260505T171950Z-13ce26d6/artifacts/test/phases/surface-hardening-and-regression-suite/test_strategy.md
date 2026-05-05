# Test Strategy

- Task ID: autoloop-v3-explicit-branch-groups-full-revised-76d1507c
- Pair: test
- Phase ID: surface-hardening-and-regression-suite
- Phase Directory Key: surface-hardening-and-regression-suite
- Phase Title: Surface Hardening And Regression Suite
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- AC-1 placeholder rendering and rooted templates:
  `tests/unit/test_primitives_and_stores.py` covers branch and fan-in artifact rendering against branch/fan-in metadata with owner-rooted relative paths.
- AC-2 additive static graph and topology metadata:
  `tests/runtime/test_runtime_static_graph.py` covers nested `branch_group` payloads, topology-hash invalidation on internal branch changes, and persisted structured `fan_out` branch inputs.
- AC-2 runtime-event coverage:
  `tests/runtime/test_runtime_tracing.py` covers emitted branch-group lifecycle events, nested step names, and evidence artifact paths through the filesystem runner.
- AC-2 branch-group runtime behavior contract:
  `tests/contract/test_branch_group_runtime.py` covers no-fan-in routing, fan-in helper exposure, request-input capture, `Goto` capture, fail-fast skipped persistence, and evidence-write failure barriers.

## Preserved Invariants Checked

- Non-branch workflow topology/static-graph contracts remain additive only.
- Branch-group topology hashes change when internal branch metadata changes.
- Persisted branch-group graph payloads remain machine-readable JSON, not Python repr strings.

## Edge Cases And Failure Paths

- Structured mapping/list/bool branch inputs survive payload serialization and file persistence.
- Fail-fast and evidence-write failure paths stay covered by existing contract tests to avoid timing or filesystem flake.

## Known Gaps

- This phase does not add new coverage for unsupported non-JSON branch inputs; compile-time validation remains covered elsewhere in the branch-group surface.
