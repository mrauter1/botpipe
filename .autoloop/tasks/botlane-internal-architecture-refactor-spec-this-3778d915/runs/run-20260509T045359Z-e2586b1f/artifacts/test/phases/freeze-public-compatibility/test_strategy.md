# Test Strategy

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: test
- Phase ID: freeze-public-compatibility
- Phase Directory Key: freeze-public-compatibility
- Phase Title: Freeze Public Compatibility
- Scope: phase-local producer artifact

## Behaviors covered

- Public root and internal-surface freeze coverage remains exercised through:
  - `tests/unit/test_simple_surface.py`
  - `tests/unit/test_sdk_facade.py`
- Strictness inventory freeze now explicitly covers the optional root scan set in `tests/strictness/test_no_compat.py`.

## Preserved invariants checked

- Test-only phase: no runtime or engine behavior changes required.
- `OPTIONAL_SCAN_FILES` points only at real root files intended for the compatibility and branding scans.
- Legacy history markdown remains excluded through `EXPLICIT_HISTORY_FILE_ALLOWLIST`.

## Edge cases

- Repo root optional scan drift: stale file names in `OPTIONAL_SCAN_FILES` now fail deterministically.
- Mixed root-vs-`legacy_docs` markdown placement remains validated by the allowlist and scan-scope tests.

## Failure paths

- Missing or renamed root optional files cause `test_optional_scan_files_match_existing_root_inventory` to fail.
- Legacy docs omitted from the explicit history allowlist still fail `test_explicit_history_allowlist_matches_legacy_docs_inventory`.

## Flake risk / stabilization

- No timing, network, or ordering sensitivity.
- Assertions read local file inventory only and use exact relative-path comparisons.

## Known gaps

- This phase does not broaden runtime coverage beyond the existing freeze buckets; it adds only the strictness guardrail needed to keep the validated baseline stable.

## Validation

- Passed: `.venv/bin/python -m pytest tests/strictness/test_no_compat.py -q`
- Passed: `.venv/bin/python -m pytest tests/unit/test_simple_surface.py tests/unit/test_sdk_facade.py tests/unit/stdlib/test_composition_helpers.py`
