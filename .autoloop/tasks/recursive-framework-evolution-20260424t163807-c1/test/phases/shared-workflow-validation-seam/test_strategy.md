# Test Strategy

- Task ID: recursive-framework-evolution-20260424t163807-c1
- Pair: test
- Phase ID: shared-workflow-validation-seam
- Phase Directory Key: shared-workflow-validation-seam
- Phase Title: Shared Workflow Validation Seam
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- `normalize_optional_string(...)`
- Happy path: trims non-empty strings
- Edge case: returns `None` for `None`
- Failure path: rejects non-strings when `coerce=False`
- Compatibility path: preserves caller-supplied `error_message`

- `normalize_unique_strings(...)`
- Happy path: preserves first-seen order while deduping normalized strings
- Edge case: supports scalar input when `allow_scalar=True`
- Failure path: rejects missing lists when `allow_none=False`
- Failure path: preserves caller-supplied `item_error_message` for strict-entry validation

- `read_json_object(...)`
- Happy path: reads JSON objects
- Failure path: rejects non-object JSON payloads

- `require_mapping(...)` and `require_mapping_list(...)`
- Happy path: normalize mapping inputs into plain dicts
- Failure path: reject non-mapping inputs
- Failure path: reject mapping-list item shape violations
- Compatibility path: preserve custom `error_message` routing through list/item failures

- `require_positive_int(...)`
- Happy path: accepts positive ints
- Failure path: rejects booleans by default
- Compatibility path: explicit `allow_bool=True` opt-in remains supported

- `stdlib.__init__` exports
- Preserved invariant: new helpers are reachable from the stdlib root surface without changing the root `workflow` surface

## Files updated

- `tests/unit/test_validation.py`
- `tests/unit/test_stdlib_and_extensions.py`

## Preserved invariants checked

- Helper seam remains additive under stdlib only.
- Existing duplicate-guard helper coverage remains intact through `require_unique_values(...)`.
- No test expectations normalize CLI/runtime/provider behavior changes.

## Known gaps

- `pytest` is not available in the current environment, so execution validation could not be completed here.
- `pydantic` is also unavailable in the bare interpreter environment, so import-level runtime smoke remains environment-blocked outside static compilation.
