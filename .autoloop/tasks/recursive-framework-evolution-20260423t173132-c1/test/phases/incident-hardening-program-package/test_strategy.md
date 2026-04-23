# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c1
- Pair: test
- Phase ID: incident-hardening-program-package
- Phase Directory Key: incident-hardening-program-package
- Phase Title: Ship Incident Hardening Workflow
- Scope: phase-local producer artifact

## Behavior-To-Test Coverage Map

- Discovery and package shape:
  - `tests/runtime/test_incident_to_hardening_program.py::test_repo_workflows_namespace_discovers_incident_hardening_package`
  - `tests/runtime/test_incident_to_hardening_program.py::test_incident_hardening_package_compiles_with_explicit_control_contracts`
- Docs and declared contract evidence:
  - `tests/runtime/test_incident_to_hardening_program.py::test_incident_hardening_package_docs_capture_decision_records`
  - `tests/test_architecture_baseline_docs.py`
- Parameter coercion and preserved invocation normalization:
  - `tests/runtime/test_incident_to_hardening_program.py::test_incident_hardening_package_rejects_blank_incident_title`
  - `tests/runtime/test_incident_to_hardening_program.py::test_incident_hardening_package_normalizes_repeatable_evidence_paths`
- Happy-path runtime proof:
  - `tests/runtime/test_incident_to_hardening_program.py::test_incident_hardening_package_runs_and_emits_terminal_receipt`
  - Covers legal route flow, terminal artifact creation, normalized route contracts, and deterministic `incident_receipt.json`
- Failure-path publish guards:
  - `tests/runtime/test_incident_to_hardening_program.py::test_incident_hardening_publish_rejects_invalid_summary_fields`
  - Covers all three publish-gating fields in `incident_summary.json`: `recommended_posture`, `primary_hypothesis`, and `hardening_backlog_items`

## Preserved Invariants Checked

- The workflow remains discoverable by canonical name and alias.
- Runtime-injected control data stays narrow and normalized on provider-owned steps.
- `incident_summary.json` remains the publication authority; invalid summary fields prevent receipt creation.
- Builder/release workflow package proofs and recursive-memory baseline still pass alongside the incident workflow tests.

## Edge Cases And Failure Paths

- Blank required workflow parameter.
- Repeatable evidence-path normalization with blanks and duplicates.
- Publish-step rejection when the machine-readable summary omits or invalidates required publication fields.

## Flake Controls

- Uses `ScriptedLLMProvider`, temp directories, and module-cache eviction for deterministic isolation.
- No timing, network, subprocess ordering, or real-provider dependencies in the incident workflow slice.

## Known Gaps

- Does not cover `recursive_autoloop/` wrapper cleanup because that remains explicitly out of scope for this phase.
- Does not add child-workflow composition tests because the workflow intentionally ships as a single package without extracted sub-workflows.
