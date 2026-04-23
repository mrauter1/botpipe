# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c2
- Pair: test
- Phase ID: proof-docs-and-recursive-memory
- Phase Directory Key: proof-docs-and-recursive-memory
- Phase Title: Close With Proof And Memory
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Stdlib helper reuse and authoring-only purity: `tests/unit/test_stdlib_and_extensions.py`
  Confirms `run_child_workflow(...)` and `adopt_child_artifacts(...)` stay additive and explicit, including failure paths already added in the earlier phase.
- Child-workflow context behavior and parent-local artifact adoption: `tests/runtime/test_workspace_and_context.py`
  Confirms child invocation remains explicit, request/workflow context stays stable, and adopted artifacts land under the parent workflow folder.
- New evidence-pack building block direct and composed behavior: `tests/runtime/test_investigation_request_to_evidence_pack.py`
  Confirms direct execution, publish-time invariants, and helper-based parent composition for `investigation_request_to_evidence_pack`.
- Builder credibility remains provable: `tests/runtime/test_workflow_builder_package.py`
  Confirms the standing workflow-builder still compiles, runs, and remains the credible baseline referenced by recursive memory.
- Baseline docs and recursive-memory closeout state: `tests/test_architecture_baseline_docs.py`
  Confirms cycle-1 and cycle-2 recursive-memory baselines, plus cycle-2 status consistency so the shipped `investigation_request_to_evidence_pack` entry does not silently drift into deferred status while `security_finding_to_verified_remediation` stays deferred.

## Preserved invariants checked

- Runtime-owned control surfaces remain limited to `expected_output_schema`, `available_routes`, and `route_contracts`.
- The closeout phase does not claim recursive wrapper/template parity when `recursive_autoloop/` remains untouched.
- `workflow_idea_to_workflow_package` remains credible while `investigation_request_to_evidence_pack` is shipped and `security_finding_to_verified_remediation` remains deferred.

## Edge cases and failure paths

- Recursive-memory drift that accidentally moves the shipped cycle-2 building block into deferred ideas.
- Recursive-memory drift that drops the chosen/deferred status distinctions inside the cycle-2 workflow candidate ledger.
- The unchanged recursive wrapper/template residual remains documented as out of scope instead of being normalized into passing expectations.

## Flake risk and stabilization

- Coverage is deterministic and file-local: scripted runtime tests plus static text assertions only.
- No network, timing, randomized ordering, or external service dependencies are introduced by this phase.

## Known gaps

- No recursive package-cli subset rerun was needed because `recursive_autoloop/` remained untouched in this phase.
- Existing `release_candidate_to_go_no_go` and `incident_to_hardening_program` workflows still are not migrated to the new building block; that remains intentionally out of scope here.
