# Test Strategy

- Task ID: recursive-framework-evolution-20260426t220607-c1
- Pair: test
- Phase ID: remaining-typed-bootstrap-convergence
- Phase Directory Key: remaining-typed-bootstrap-convergence
- Phase Title: Finish Typed Bootstrap Convergence
- Scope: phase-local producer artifact

## Behavior-to-Test Coverage Map

- AC-1: typed bootstrap projection replaces raw bootstrap normalization
  - Covered by:
    - `tests/runtime/test_release_candidate_to_go_no_go.py::test_release_go_no_go_bootstrap_reads_typed_ctx_params`
    - `tests/runtime/test_investigation_request_to_evidence_pack.py::test_investigation_evidence_pack_bootstrap_reads_typed_ctx_params`
    - `tests/runtime/test_security_finding_to_verified_remediation.py::test_security_remediation_bootstrap_reads_typed_ctx_params`
    - `tests/runtime/test_incident_to_hardening_program.py::test_incident_hardening_bootstrap_reads_typed_ctx_params`
    - `tests/runtime/test_workflow_builder_package.py::test_workflow_builder_package_bootstrap_reads_typed_ctx_params`
  - Edge case:
    - Each test passes contradictory raw `workflow_params` alongside typed `params` to prove bootstrap logic ignores the raw dict when `Parameters` exists.

- AC-2: preserved workflow behavior and compatibility
  - Covered by existing end-to-end receipt/invocation-contract suites in the same five runtime test modules.
  - Preserved invariants checked:
    - workflow-specific invocation-contract fields remain unchanged
    - session opening still happens in bootstrap
    - runtime-owned invocation metadata still exists via `write_invocation_contract(...)`
    - route names, artifact names, receipts, and child-composition flows remain on the existing happy path

- AC-3: proof plus standing docs/memory agree on the completed migration
  - Covered by:
    - `tests/test_architecture_baseline_docs.py::test_recursive_memory_records_remaining_typed_bootstrap_convergence_closeout`
    - targeted proof run:
      - `.venv/bin/pytest -q tests/runtime/test_release_candidate_to_go_no_go.py tests/runtime/test_investigation_request_to_evidence_pack.py tests/runtime/test_security_finding_to_verified_remediation.py tests/runtime/test_incident_to_hardening_program.py tests/runtime/test_workflow_builder_package.py tests/test_architecture_baseline_docs.py`

## Failure Paths Covered

- Existing parameter-validation tests in the five runtime suites still cover invalid or blank required parameter input.
- The new bootstrap tests would fail if any scoped workflow reintroduced raw `ctx.workflow_params` reads.

## Determinism / Flake Control

- Bootstrap regression tests use direct `Context(...)` construction plus `InMemorySessionStore()` and filesystem-local temp directories only.
- No network, timing, subprocess ordering, or nondeterministic provider behavior is involved in the new regression checks.

## Known Gaps

- No extra failure-path tests were added for publish handlers because this phase does not change publish behavior and those paths are already covered by the existing runtime suites.
