# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c11
- Pair: test
- Phase ID: decomposition-surface-seam
- Phase Directory Key: decomposition-surface-seam
- Phase Title: Add Decomposition Surface Seam
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Happy path: `test_decomposition_helper_writes_selected_workflow_identity_authoring_surface_and_compiled_routes`
  Covers combined identity + authoring-surface + compiled step/route payload, repo-relative path metadata, stdlib export seam usage, and read-only behavior.
- Edge case: `test_decomposition_helper_keeps_optional_authoring_paths_nullable_when_absent`
  Covers absent `params.py`, `contracts.py`, docs, runtime test, and asset folders without widening the payload contract.
- Edge case: `test_decomposition_helper_reports_empty_parameter_metadata_when_selected_workflow_has_no_params_model`
  Covers preserved compiled-surface behavior when the selected workflow exports no parameters model.
- Edge case: `test_decomposition_helper_accepts_main_workflow_class_references`
  Covers main-workflow-class resolution plus compiled prompt repo-relative metadata.
- Failure paths: path-escape and non-JSON output-path validation inside `test_decomposition_helper_writes_selected_workflow_identity_authoring_surface_and_compiled_routes`.
- Baseline docs: decomposition helper boundary assertions in `tests/test_architecture_baseline_docs.py`.

## Preserved invariants checked

- Helper writes only under `ctx.workflow_folder`.
- Helper does not mutate selected workflow package files.
- Helper stays additive, read-only, and outside runtime-owned control contracts.
- No new `workflow.toml` fields or runtime-owned decomposition behavior are encoded in tests.

## Reliability / stabilization

- Uses local temporary repositories and fixture-generated workflow packages only.
- No timing, network, subprocess orchestration, or nondeterministic ordering dependencies beyond explicit sorted path expectations.

## Known gaps

- No broader runtime integration test was added because this phase is explicitly authoring-only and the unit + baseline-doc coverage already exercises the delivered contract.
