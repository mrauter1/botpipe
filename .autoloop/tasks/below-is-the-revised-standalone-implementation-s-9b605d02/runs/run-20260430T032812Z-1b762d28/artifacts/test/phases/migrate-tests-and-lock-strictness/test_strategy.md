# Test Strategy

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: test
- Phase ID: migrate-tests-and-lock-strictness
- Phase Directory Key: migrate-tests-and-lock-strictness
- Phase Title: Migrate Tests And Strictness
- Scope: phase-local producer artifact

## Behavior-to-coverage map
- AC-1 maintained canonical authoring surface:
  - `tests/unit/test_validation.py`
  - `tests/contract/test_engine_contracts.py`
  - `tests/runtime/test_compatibility_runtime.py`
  - `tests/fixtures/toy_runtime_workflow.py`
  - Coverage method: maintained-tree banned-vocabulary scan plus explicit scan-scope assertions in `tests/strictness/test_no_compat.py`.
- AC-2 strictness boundary:
  - `tests/strictness/test_no_compat.py::test_removed_compatibility_scan_scope_covers_maintained_tree_only`
  - `tests/strictness/test_no_compat.py::test_active_tree_does_not_reintroduce_removed_compatibility_surfaces`
  - Coverage method: verify only the strictness file is excluded by default, persisted-compatibility fixture exclusions stay explicit and empty, and maintained targets including `tests/contract/test_engine_contracts.py` remain inside the scan.
- AC-3 targeted verification suite:
  - `tests/unit/test_validation.py`
  - `tests/contract/test_engine_contracts.py`
  - `tests/runtime/test_compatibility_runtime.py`
  - `tests/runtime/test_runtime_static_graph.py`
  - `tests/runtime/test_provider_backends.py`
  - `tests/strictness/test_no_compat.py`

## Preserved invariants checked
- Compatibility runtime coverage remains in the maintained scan surface even though legacy persisted-reader payload behavior is still supported.
- `core/_compat.py` remains part of the maintained scan surface after the implementer removed the blanket carve-out.
- No new fixture-level exclusions are needed for this phase.

## Edge cases / failure paths
- Scan-scope regression: if a required maintained suite falls out of `ACTIVE_SCAN_ROOTS` or gets added to exclusions, the strictness scope test fails.
- Vocabulary regression: if active `produces`, `review_produces`, `do_produces`, or `.produces` usage reappears in maintained files, the strictness scan fails.

## Flake risk / stabilization
- No timing, network, or nondeterministic ordering dependencies.
- Coverage relies on deterministic repository file enumeration and targeted local pytest execution through `.venv/bin/python -m pytest`.

## Known gaps
- The strictness suite validates maintained-tree scan coverage rather than creating synthetic persisted-reader fixture exclusions; that boundary remains intentionally empty in this phase.
