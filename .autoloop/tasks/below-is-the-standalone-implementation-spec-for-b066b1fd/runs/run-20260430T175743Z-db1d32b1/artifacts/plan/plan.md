# Simple Surface Signature Coverage Plan

## Objective
Align the maintained simple-surface signature coverage with the implemented scoped-state API by updating canonical signature expectations, while preserving the shipped public authoring behavior in `autoloop/simple.py`.

## Scope
- Update `tests/unit/test_simple_surface.py::test_canonical_simple_signatures_expose_only_canonical_argument_names` so `simple.step` and `simple.produce_verify_step` expect the implemented canonical parameter lists, including `scope`, `item_state`, and `state` where applicable.
- Keep `python_step(...)` signature coverage aligned with the current implementation.
- Re-run the focused simple-surface unit suite that previously surfaced the single signature failure.

## Out Of Scope
- Behavior changes to `autoloop/simple.py` authoring factories when signatures already match the implemented API.
- Reopening bridge-removal, hook-rerouting, state, scoped-state, required-write, or history work unless the signature check exposes a separate concrete mismatch.

## Milestone
### Refresh maintained signature assertions
- Treat the current factory signatures in `autoloop/simple.py` as authoritative for this task because they already expose the requested scoped-state keywords.
- Update the test’s canonical parameter-name tuples to match the required public signatures:
  - `step(prompt, *, name, reads, requires, writes, scope, item_state, routes, before, after, on_route, control_schema, retry, session, control_routes)`
  - `produce_verify_step(*, producer_prompt, verifier_prompt, name, reads, requires, verifier_reads, verifier_requires, producer_writes, verifier_writes, scope, routes, state, item_state, before_producer, after_producer, before_verifier, after_verifier, on_route, control_schema, retry, session, verifier_session, control_routes)`
- Leave the `python_step` expectation unchanged unless the focused suite reveals an actual mismatch.

## Interface And Compatibility Notes
- Public simple authoring behavior remains unchanged; this task updates maintained signature coverage rather than broadening or narrowing accepted keywords.
- Parameter order matters because the test explicitly validates the canonical `inspect.signature(...)` surface; preserve the implemented order already present in `autoloop/simple.py`.
- No migration or rollout work is required because no shipped runtime behavior is expected to change.

## Validation
- Reproduce the current failure with:
  - `.venv/bin/python -m pytest -q tests/unit/test_simple_surface.py -k canonical_simple_signatures_expose_only_canonical_argument_names`
- After updating the maintained expectations, verify the focused suite is fully green with:
  - `.venv/bin/python -m pytest -q tests/unit/test_simple_surface.py`

## Regression Risk Notes
- Primary risk: accidentally editing `autoloop/simple.py` and changing the public authoring surface instead of only fixing maintained coverage.
- Secondary risk: updating only one signature tuple and leaving `step`, `produce_verify_step`, and `python_step` coverage inconsistent.
- Control: keep code changes local to `tests/unit/test_simple_surface.py` unless a newly reproduced signature mismatch proves the implementation itself is wrong.

## Risk Register
- Risk: signature tuple order drifts from the implemented factories.
  Mitigation: use `inspect.signature(simple.step)` and `inspect.signature(simple.produce_verify_step)` as the source of truth before editing the assertions.
- Risk: focused verification uses the wrong interpreter and masks failures.
  Mitigation: run tests through `.venv/bin/python -m pytest`.
- Risk: scope expands into unrelated state/history work.
  Mitigation: defer any non-signature follow-up unless the focused test run reveals a new concrete mismatch tied to this surface.

## Rollback
- Revert the test expectation changes in `tests/unit/test_simple_surface.py` if they expose a broader implementation inconsistency that was not part of this request.
