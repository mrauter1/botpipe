# Test Strategy

- Task ID: below-is-the-standalone-implementation-spec-for-b066b1fd
- Pair: test
- Phase ID: refresh-simple-signature-coverage
- Phase Directory Key: refresh-simple-signature-coverage
- Phase Title: Refresh Simple Signature Coverage
- Scope: phase-local producer artifact

## Behavior-To-Test Coverage Map
- `simple.step` canonical signature coverage: `tests/unit/test_simple_surface.py::test_canonical_simple_signatures_expose_only_canonical_argument_names` asserts `scope` and `item_state` are present in the implemented order.
- `simple.produce_verify_step` canonical signature coverage: the same test asserts `scope`, `state`, and `item_state` are present in the implemented order.
- `simple.python_step` preserved signature coverage: the same test keeps the existing canonical tuple unchanged to catch unintended drift in adjacent simple-surface signature coverage.

## Preserved Invariants Checked
- `autoloop/simple.py` remains the authoritative shipped authoring surface for this phase.
- No new legacy aliases or alternate parameter names are normalized by the signature assertions.
- Focus remains on maintained coverage only, not behavior changes in the simple factories.

## Edge Cases
- Parameter order is validated exactly via `inspect.signature(...)` tuple equality, which catches both missing names and ordering drift.
- The assertions cover the keyword-only shape indirectly by checking the exported parameter sequence after `*`.

## Failure Paths
- If `scope`, `state`, or `item_state` are removed or reordered in the exported factories, the canonical signature test fails immediately.
- If `python_step(...)` drifts while touching adjacent coverage, the unchanged tuple assertion fails and blocks accidental collateral updates.

## Validation
- `.venv/bin/python -m pytest -q tests/unit/test_simple_surface.py` -> `34 passed`.

## Flake Risk / Stabilization
- Low flake risk: coverage is pure signature inspection with no timing, network, filesystem mutation, or nondeterministic ordering dependencies.
- Stable interpreter selection is enforced by using `.venv/bin/python` because `python` and `pytest` are not on PATH in this shell.

## Known Gaps
- No broader API-behavior tests were added because the request was limited to maintained signature coverage and the existing focused test already exercises the intended regression surface.
