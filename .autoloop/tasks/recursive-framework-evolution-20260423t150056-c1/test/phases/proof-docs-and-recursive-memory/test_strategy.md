# Test Strategy

- Task ID: recursive-framework-evolution-20260423t150056-c1
- Pair: test
- Phase ID: proof-docs-and-recursive-memory
- Phase Directory Key: proof-docs-and-recursive-memory
- Phase Title: Close With Proof And Memory
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Closeout proof surface remains green for the shipped route-contract seam and release workflow package.
  - Coverage: `.venv/bin/pytest -q tests/runtime/test_release_candidate_to_go_no_go.py tests/runtime/test_workflow_builder_package.py tests/unit/test_validation.py tests/contract/test_engine_contracts.py tests/test_architecture_baseline_docs.py`

- Standing recursive memory records the cycle-one closeout baseline.
  - Coverage: `tests/test_architecture_baseline_docs.py::test_recursive_memory_files_record_cycle_one_closeout_baseline`
  - Behaviors checked: builder credibility, narrow runtime control contract terms, route-contract improvement, release workflow choice, deferred incident workflow, and explicit wrapper/template residual.

- Standing recursive memory does not silently leave the release workflow marked as deferred.
  - Coverage: `tests/test_architecture_baseline_docs.py::test_recursive_memory_closeout_statuses_do_not_leave_release_marked_deferred`
  - Behaviors checked: `framework_roadmap.md` keeps `incident_to_hardening_program` in `Deferred Ideas` but excludes `release_candidate_to_go_no_go`; `workflow_candidate_ledger.md` still marks release as shipped and incident as deferred.

## Preserved invariants checked

- The proof-docs closeout phase does not claim package-CLI wrapper/template parity; the residual remains explicitly documented.
- Existing route-contract and release-workflow proof remains green after the standing-memory edits.

## Edge cases and failure paths

- Stale closeout memory that mentions the release workflow but still leaves it under `Deferred Ideas`.
- Candidate-ledger drift where both release and incident are present but their chosen/deferred statuses regress.
- Missing required closeout strings in any of the four standing memory files.

## Flake risk and stabilization

- Tests are filesystem-only string/section assertions plus deterministic scripted-provider/runtime suites already used elsewhere in the cycle.
- No network, timing, or nondeterministic ordering dependencies were added.

## Known gaps

- `tests/runtime/test_package_cli.py` remains intentionally out of scope for this phase because `recursive_autoloop/` wrapper/template parity was explicitly deferred.
