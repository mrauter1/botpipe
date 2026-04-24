# Test Strategy

- Task ID: recursive-framework-evolution-20260424t163807-c2
- Pair: test
- Phase ID: proof-docs-and-memory-sync
- Phase Directory Key: proof-docs-and-memory-sync
- Phase Title: Prove And Record Consolidation
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- Shared validation helper surface
  Covered by `tests/unit/test_validation.py` and `tests/unit/test_stdlib_and_extensions.py`
  Checks happy-path imports and values for `require_non_negative_int(...)`, shared helper exports, and failure paths for negative integers, bool coercion boundaries, and non-object mappings.
- Migrated workflow publication paths
  Covered by `tests/runtime/test_investigation_request_to_evidence_pack.py`, `tests/runtime/test_security_finding_to_verified_remediation.py`, `tests/runtime/test_release_candidate_to_go_no_go.py`, and `tests/runtime/test_incident_to_hardening_program.py`
  Checks terminal publication receipts, preserved artifact names, preserved route contracts, and the domain-specific publish invariants that remained workflow-local after the validation migration.
- Authoring-doc validation-boundary alignment
  Covered by `tests/test_architecture_baseline_docs.py::test_authoring_doc_describes_shared_validation_helper_boundary`
  Checks that `docs/authoring.md` names `require_non_negative_int` and keeps the generic-vs-domain validation boundary explicit.
- Recursive-memory closeout sync
  Covered by `tests/test_architecture_baseline_docs.py::test_recursive_memory_records_cycle_fourteen_proof_and_remaining_validation_debt`
  Checks that cycle 14 memory now records the proof/docs sync, the compatibility freeze, the resolved older-domain validation wave, and the remaining deferred `params.py` validator debt.

## Preserved Invariants Checked

- No CLI, runtime-routing, `ctx.invoke_workflow(...)`, or workflow-artifact contract change is normalized by the tests.
- Artifact names, receipt names, and route contracts for the four migrated workflows remain unchanged.
- Remaining deferred debt stays focused on repeated `params.py` validators rather than reopening the resolved workflow-local validation wave.

## Edge Cases And Failure Paths

- Negative-int rejection and bool handling for shared validation helpers.
- Non-object JSON / mapping-list validation failures in shared helper coverage.
- Workflow publish paths still reject malformed summaries or missing authoritative artifacts through the runtime suites that already exercise the domain-specific validation branches.
- Recursive-memory regression guard catches loss of the cycle-14 closeout note, missing compatibility-freeze language, or accidental removal of the deferred-debt record.

## Flake Risk And Stabilization

- No timing or network risk introduced.
- Coverage relies on deterministic fake-provider/runtime fixtures and static document text assertions only.

## Known Gaps

- This phase does not broaden runtime coverage beyond the four workflows touched by the earlier migration because the proof/docs sync itself is documentation-only.
- Repeated `workflows/*/params.py` validator normalization remains intentionally deferred to a future authoring-surface cycle.
