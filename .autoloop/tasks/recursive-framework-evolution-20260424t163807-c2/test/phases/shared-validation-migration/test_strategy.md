# Test Strategy

- Task ID: recursive-framework-evolution-20260424t163807-c2
- Pair: test
- Phase ID: shared-validation-migration
- Phase Directory Key: shared-validation-migration
- Phase Title: Migrate Older Domain Validation
- Scope: phase-local producer artifact

## Behavior To Test Coverage Map

- Shared validation seam additions
  Covered by `tests/unit/test_validation.py` and `tests/unit/test_stdlib_and_extensions.py` for `require_non_negative_int(...)`, JSON-object reads, shared export wiring, and strict failure messages.
- Older domain workflow migration
  Covered by `tests/runtime/test_investigation_request_to_evidence_pack.py`, `tests/runtime/test_security_finding_to_verified_remediation.py`, `tests/runtime/test_release_candidate_to_go_no_go.py`, and `tests/runtime/test_incident_to_hardening_program.py` for terminal receipt publication and invalid summary rejection.
- Preserved publication invariants after reviewer fix
  Covered by release/incident runtime tests that reject missing, numeric, and boolean publish-time summary strings while still accepting valid string summaries.
- Snapshot-helper direct seam reuse
  Covered indirectly by existing status/task-id filter tests in `tests/unit/test_stdlib_and_extensions.py` and `tests/runtime/test_workspace_and_context.py`; no new helper surface was introduced.

## Edge Cases

- Non-negative integer helper accepts `0` and rejects negative values and `bool`.
- Publish-time summary validation rejects non-string values that shared helpers might otherwise coerce.
- Invalid JSON-object shape still fails through the shared seam with deterministic messages.

## Failure Paths

- Missing required release recommendation blocks receipt publication.
- Missing or non-string incident posture / primary hypothesis blocks receipt publication.
- Negative incident backlog counts still fail publication.

## Known Gaps

- No separate test was added for `stdlib/company.py`, `stdlib/diagnostics.py`, and `stdlib/portfolio.py` beyond existing filter-validation coverage because the cleanup was a direct call-site reuse of already-tested strict string filtering.
- This phase does not broaden into `params.py` validator deduplication coverage because that work remains out of scope.
