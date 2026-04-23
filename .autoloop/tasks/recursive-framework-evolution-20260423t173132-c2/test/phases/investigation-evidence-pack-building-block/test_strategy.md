# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c2
- Pair: test
- Phase ID: investigation-evidence-pack-building-block
- Phase Directory Key: investigation-evidence-pack-building-block
- Phase Title: Ship Investigation Evidence-Pack Building Block
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Discovery and package contract
  - `test_repo_workflows_namespace_discovers_investigation_evidence_pack_package`
  - `test_investigation_evidence_pack_package_compiles_with_explicit_control_contracts`
  - `test_investigation_evidence_pack_package_docs_capture_decision_records`
- Direct runtime behavior
  - `test_investigation_evidence_pack_package_runs_and_emits_terminal_receipt`
  - proves legal route flow, terminal artifacts, and deterministic `evidence_pack_receipt.json`
- Composed runtime behavior
  - `test_investigation_evidence_pack_package_can_be_composed_through_helper_seam`
  - proves helper-based child invocation, parent-local artifact adoption, and child-run metadata/artifact paths
- Parameter and input edge cases
  - `test_investigation_evidence_pack_package_rejects_blank_investigation_title`
  - `test_investigation_evidence_pack_package_normalizes_repeatable_inputs`
- Publication failure paths
  - `test_investigation_evidence_pack_publish_rejects_invalid_machine_readable_summary`
  - covers missing `ready_for_downstream_assessment` and `investigation_kind` mismatch between state and `evidence_pack_summary.json`

## Preserved invariants checked

- Runtime-owned control surfaces remain on `expected_output_schema`, `available_routes`, and `route_contracts`.
- Composition stays authoring-only through `run_child_workflow(...)` and `adopt_child_artifacts(...)`; no new runtime step type is assumed in tests.
- Child artifacts remain workflow-local while adopted parent copies remain under `ctx.workflow_folder`.

## Failure-path and edge-case focus

- Blank required workflow parameters fail validation deterministically.
- Repeatable list inputs normalize whitespace and duplicates.
- Publish fails closed when the machine-readable summary is incomplete or inconsistent with workflow state.

## Stabilization notes

- All runtime proofs use `ScriptedLLMProvider` and fixture packages under `tmp_path`; no timing, network, or nondeterministic ordering dependencies are introduced.

## Known gaps

- No migration tests for `release_candidate_to_go_no_go` or `incident_to_hardening_program`, because that work is explicitly out of scope for this phase.
