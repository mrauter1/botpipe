# Test Strategy

- Task ID: recursive-framework-evolution-20260424t163807-c3
- Pair: test
- Phase ID: shared-parameter-validator-seam
- Phase Directory Key: shared-parameter-validator-seam
- Phase Title: Shared Parameter Validator Seam
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Additive stdlib seam exists under `stdlib/validation.py`
  - Coverage: import/use the new helper factories in `tests/unit/test_validation.py`
  - Preserved invariant: no runtime-owned parameter coercion test expectations changed

- Re-export surface exists under `stdlib/__init__.py`
  - Coverage: `tests/unit/test_stdlib_and_extensions.py` asserts the exported helpers resolve to the same validation-module symbols
  - Preserved invariant: stdlib remains the only public seam widened in this phase

- Required/optional/list/int helper behavior matches the copied `params.py` patterns
  - Happy paths: whitespace trimming, blank-to-`None`, order-preserving dedupe, positive integer acceptance
  - Failure paths: non-empty required text failures, positive-int failures, preserved custom error-message paths

- Multi-field validator reuse works for the same descriptor
  - Coverage: `tests/unit/test_validation.py` now exercises one model that binds each helper across multiple fields, matching the repeated `@field_validator("a", "b", ...)` pattern in `workflows/*/params.py`
  - Edge case: one optional multi-field input normalizes blank text to `None`

## Validation run

- Command: `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/unit/test_validation.py tests/unit/test_stdlib_and_extensions.py`
- Result: `91 passed`

## Known gaps

- No runtime workflow suites were rerun in this phase because no `workflows/*/params.py` files were migrated yet.
- `docs/authoring.md` examples remain deferred until the later migration phase can show real helper adoption in workflow parameter models.
