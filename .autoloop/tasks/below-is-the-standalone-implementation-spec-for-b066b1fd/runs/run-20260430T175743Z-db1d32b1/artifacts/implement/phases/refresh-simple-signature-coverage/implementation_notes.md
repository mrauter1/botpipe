# Implementation Notes

- Task ID: below-is-the-standalone-implementation-spec-for-b066b1fd
- Pair: implement
- Phase ID: refresh-simple-signature-coverage
- Phase Directory Key: refresh-simple-signature-coverage
- Phase Title: Refresh Simple Signature Coverage
- Scope: phase-local producer artifact

## Files Changed
- `tests/unit/test_simple_surface.py`
- `.autoloop/tasks/below-is-the-standalone-implementation-spec-for-b066b1fd/runs/run-20260430T175743Z-db1d32b1/artifacts/implement/phases/refresh-simple-signature-coverage/implementation_notes.md`

## Symbols Touched
- `test_canonical_simple_signatures_expose_only_canonical_argument_names`

## Checklist Mapping
- Canonical `simple.step` signature assertion updated to include `scope` and `item_state` in implemented order.
- Canonical `simple.produce_verify_step` signature assertion updated to include `scope`, `state`, and `item_state` in implemented order.
- `simple.python_step` signature assertion left unchanged because it already matches the current implementation.
- Focused validation run executed with `.venv/bin/python -m pytest -q tests/unit/test_simple_surface.py`.

## Assumptions
- The exported factory signatures in `autoloop/simple.py` remain the authoritative public surface for this task.

## Preserved Invariants
- No changes to shipped authoring behavior in `autoloop/simple.py`.
- No expansion into bridge-removal, hook-rerouting, state, scoped-state, required-write, or history work.

## Intended Behavior Changes
- Maintained signature coverage now reflects the implemented scoped-state API surface.

## Known Non-Changes
- `autoloop/simple.py` was not edited.
- `python_step(...)` coverage order was not changed.

## Expected Side Effects
- `test_canonical_simple_signatures_expose_only_canonical_argument_names` should stop failing on the scoped-state parameter order drift.

## Validation Performed
- Reproduced the original failure with `.venv/bin/python -m pytest -q tests/unit/test_simple_surface.py -k canonical_simple_signatures_expose_only_canonical_argument_names`.
- Verified the focused suite passes with `.venv/bin/python -m pytest -q tests/unit/test_simple_surface.py` (`34 passed`).

## Deduplication / Centralization
- Kept the change local to maintained test expectations rather than duplicating signature definitions elsewhere.
