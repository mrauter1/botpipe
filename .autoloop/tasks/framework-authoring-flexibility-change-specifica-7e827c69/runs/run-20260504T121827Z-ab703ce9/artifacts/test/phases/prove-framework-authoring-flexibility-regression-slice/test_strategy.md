# Test Strategy

- Task ID: framework-authoring-flexibility-change-specifica-7e827c69
- Pair: test
- Phase ID: prove-framework-authoring-flexibility-regression-slice
- Phase Directory Key: prove-framework-authoring-flexibility-regression-slice
- Phase Title: Run, Repair, and Record Acceptance Slice
- Scope: phase-local producer artifact

## Behavior-to-test coverage map
- Managed-artifact diagnostic wording:
  Covered by `tests/unit/test_validation.py::test_validation_rejects_same_identity_artifact_declared_workflow_level_and_produced`.
  Checks the ambiguity error now mentions `Artifact.managed(...)` and `role='managed'`, and rejects the removed `once implemented` phrasing.
- Shared ambiguity helper across ownership shapes:
  Covered by `tests/unit/test_validation.py::test_validation_rejects_distinct_artifacts_with_same_public_name_across_workflow_and_step_output`.
  Confirms the alternate workflow-level-vs-produced collision path still uses the same diagnostic family and includes the managed-artifact surface.
- Preserved route metadata invariants:
  Covered by the required slice command over `tests/contract/test_engine_contracts.py`, `tests/unit/test_simple_surface.py`, `tests/unit/test_primitives_and_stores.py`, `tests/unit/test_validation.py`, and `tests/runtime/test_runtime_static_graph.py`.
  Validates provider-visible route metadata, required-write reporting, and adjacent authoring contracts remain stable.

## Edge cases
- Same artifact object reused as both workflow-level declaration and step write.
- Distinct artifact objects sharing the same public name across workflow-level and produced scopes.

## Failure paths
- Ambiguous ownership still raises `WorkflowValidationError`.
- The diagnostic must no longer imply managed artifacts are unimplemented future work.

## Known gaps
- No additional docs suite coverage is added here because the requested acceptance slice already carries the wording regression through `tests/unit/test_validation.py`.

## Flake risk / stabilization
- Low flake risk: all covered checks are deterministic exception-message assertions and local pytest runs in the repository venv.
