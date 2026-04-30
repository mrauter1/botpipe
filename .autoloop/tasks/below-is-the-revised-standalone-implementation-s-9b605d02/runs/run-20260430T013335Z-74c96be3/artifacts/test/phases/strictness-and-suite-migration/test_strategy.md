# Test Strategy

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: test
- Phase ID: strictness-and-suite-migration
- Phase Directory Key: strictness-and-suite-migration
- Phase Title: Migrate Active Suites And Tighten Strictness
- Scope: phase-local producer artifact

## Behavior coverage map

- Strictness boundary:
  Active strictness coverage scans `autoloop/`, `core/`, `runtime/`, `stdlib/`, repo-root `workflows/`, docs, and active tests while excluding only explicit compatibility fixtures.
- Canonical active suite vocabulary:
  Active unit and contract suites assert canonical `FINISH` and `required_writes` surfaces instead of legacy `SUCCESS`, `required_outputs`, or removed helper aliases.
- Compiled-route public surface:
  `tests/unit/test_validation.py` now verifies that unspecified routes and explicit `required_writes=[]` routes both expose tuple-shaped public `required_writes`, preventing regressions that leak `None` through active compiled metadata.
- Runtime explicit-empty override:
  `tests/contract/test_engine_contracts.py` preserves the runtime behavior that explicit `required_writes=[]` suppresses artifact-level required defaults while unspecified routes still inherit them.
- Compatibility quarantine:
  `tests/runtime/test_compatibility_runtime.py` remains the explicit compatibility suite, while active suites and fixtures stay on canonical in-memory authoring vocabulary.

## Preserved invariants checked

- Public compiled routes expose stable tuple `required_writes`.
- Runtime still distinguishes explicit empty route contracts from unspecified defaults.
- The compatibility boundary remains explicit rather than broadening strictness exclusions.

## Edge cases

- Route metadata omitted entirely versus route metadata present with an explicit empty `required_writes=[]`.
- Active strictness scans containing fragmented removed-name assertions without reintroducing banned literals.

## Failure paths

- A future regression that changes public compiled routes back to `None`-shaped `required_writes` fails the new focused unit test.
- A future regression that loses explicit-empty override behavior still fails the existing engine contract test.

## Known gaps

- This turn did not add new coverage outside the route-required-writes regression seam because the broader strictness and canonical verification slices already exist and are exercised by the implementation phase validation.
