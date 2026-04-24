# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c6
- Pair: test
- Phase ID: selected-workflow-adaptation-seam
- Phase Directory Key: selected-workflow-adaptation-seam
- Phase Title: Selected Workflow Adaptation Seam
- Scope: phase-local producer artifact

## Behaviors covered

- `write_selected_workflow_capability_snapshot(...)` writes the selected-workflow contract artifact under `ctx.workflow_folder`.
- `write_selected_workflow_capability_snapshot(...)` resolves a selected workflow by alias without importing unrelated workflow packages.
- `write_validated_workflow_parameters(...)` writes validated parameter artifacts under `ctx.workflow_folder`.
- `write_validated_workflow_parameters(...)` delegates to the shared loader coercion path for both success and failure semantics.
- `docs/authoring.md` and `tests/unit/test_stdlib_and_extensions.py` describe the seam as additive and authoring-only.

## Preserved invariants checked

- Workflow-local JSON helpers still reject path escape attempts and non-`.json` targets.
- The seam does not add runtime-owned auto-adaptation or broaden runtime control contracts.
- Existing stdlib purity expectations still hold for `stdlib/adaptation.py`.

## Edge cases

- Selected-workflow capability snapshot against a repo that also contains an unrelated workflow package whose `workflow.py` would fail if imported.
- Workflow-local nested output paths for selected snapshot and validated parameter artifacts.

## Failure paths

- Rejected path escape attempts for both new helper entrypoints.
- Rejected non-`.json` artifact targets for both new helper entrypoints.
- Unknown workflow parameters surface the shared `WorkflowParameterError` from the loader path instead of helper-local validation.

## Validation run

- `.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py`
- `.venv/bin/pytest -q tests/test_architecture_baseline_docs.py`

## Known gaps

- No dedicated test yet for class-based selected-workflow references; current coverage exercises canonical/alias string resolution only.
