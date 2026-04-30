# Original intent considered

- Update the maintained canonical signature coverage in `tests/unit/test_simple_surface.py::test_canonical_simple_signatures_expose_only_canonical_argument_names`.
- Preserve the shipped public authoring surface in `autoloop/simple.py`.
- Ensure the canonical `step(...)` and `produce_verify_step(...)` expectations include the scoped-state parameters in the requested order.
- Keep `python_step(...)` signature coverage aligned with the existing implementation.
- Re-run the focused simple-surface suite and confirm the prior single failure is fully resolved.

# Clarifications / superseding decisions

- No later clarification in `raw_phase_log.md` changed user intent.
- `decisions.txt` records that the exported factory signatures in `autoloop/simple.py` are authoritative for this task and that changes should stay limited to maintained signature coverage unless focused validation reveals another mismatch.
- `decisions.txt` also records the environment-specific validation command: `.venv/bin/python -m pytest`.
- The test phase recorded an intentional scope limit: do not broaden test coverage beyond the existing canonical signature assertion for this run.

# Implemented behavior

- `tests/unit/test_simple_surface.py` now expects `simple.step` parameters `("prompt", "name", "reads", "requires", "writes", "scope", "item_state", "routes", "before", "after", "on_route", "control_schema", "retry", "session", "control_routes")`.
- The same test now expects `simple.produce_verify_step` parameters `("producer_prompt", "verifier_prompt", "name", "reads", "requires", "verifier_reads", "verifier_requires", "producer_writes", "verifier_writes", "scope", "routes", "state", "item_state", "before_producer", "after_producer", "before_verifier", "after_verifier", "on_route", "control_schema", "retry", "session", "verifier_session", "control_routes")`.
- `python_step(...)` coverage remains unchanged and still matches the live signature.
- `autoloop/simple.py` already exposes the requested public signatures and was not modified.
- Live verification in the final codebase:
  - `inspect.signature(simple.step)`, `inspect.signature(simple.produce_verify_step)`, and `inspect.signature(simple.python_step)` match the maintained tuples.
  - `.venv/bin/python -m pytest -q tests/unit/test_simple_surface.py` passes with `34 passed in 0.48s`.

# Unresolved gaps

- None. The final codebase and focused validation satisfy the requested signature coverage update without changing shipped authoring behavior.

# Differences justified by later clarification or analysis

- The implementation change stayed in `tests/unit/test_simple_surface.py` rather than `autoloop/simple.py` because direct inspection showed the public factories already matched the requested scoped-state API. This is consistent with the request to preserve shipped authoring behavior.
- Validation remained focused on `tests/unit/test_simple_surface.py` because the request described one known failing assertion and the later run decisions explicitly constrained scope to maintained signature coverage.

# Recommended next run

- No follow-up implementation run is required for this request.
