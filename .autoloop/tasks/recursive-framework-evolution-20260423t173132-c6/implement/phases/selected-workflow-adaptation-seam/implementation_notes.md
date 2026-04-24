# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t173132-c6
- Pair: implement
- Phase ID: selected-workflow-adaptation-seam
- Phase Directory Key: selected-workflow-adaptation-seam
- Phase Title: Selected Workflow Adaptation Seam
- Scope: phase-local producer artifact

## Files changed

- `stdlib/adaptation.py`
- `stdlib/__init__.py`
- `docs/authoring.md`
- `tests/unit/test_stdlib_and_extensions.py`

## Symbols touched

- `write_selected_workflow_capability_snapshot`
- `write_validated_workflow_parameters`
- `test_adaptation_helpers_snapshot_one_selected_workflow_without_importing_unrelated_packages`
- `test_adaptation_helpers_delegate_parameter_validation_to_shared_loader_coercion_path`
- `_build_lifecycle_context`

## Checklist mapping

- Phase 1 / add `stdlib/adaptation.py` and exports: complete
- Phase 1 / document the seam in `docs/authoring.md`: complete
- Phase 1 / extend unit coverage for locality, resolution, and validation reuse: complete
- Phase 1 / avoid CLI, runtime, or manifest changes: preserved

## Assumptions

- The current repo-root `core/`, `runtime/`, `stdlib/`, and `workflows/` layout is the authoritative replacement for the stale `src/autoloop/...` paths in the original request.
- Selected-workflow contract capture should resolve exactly one workflow and should not require importing unrelated workflow packages.

## Preserved invariants

- Helper writes remain constrained to `ctx.workflow_folder` via the existing workflow-local JSON writer.
- Workflow parameter validation still flows through `runtime.loader.coerce_workflow_parameter_mapping`.
- No CLI syntax, `workflow.toml`, runtime routing, or auto-adaptation behavior changed.

## Intended behavior changes

- Workflow authors now have an additive stdlib seam for:
- capturing one selected workflow capability snapshot as a workflow-local JSON artifact
- writing a validated workflow-parameter artifact for a selected workflow without duplicating coercion logic

## Known non-changes

- No new workflow package was added in this phase.
- No runtime-owned routing, publication, or execution semantics were widened.
- No task-to-workflow-strategy handoff behavior changed in this phase.

## Expected side effects

- Adaptation-oriented workflows can reuse a selected-workflow snapshot/validation seam without importing the full portfolio capability helper.
- Unit coverage now guards against path escape attempts and accidental divergence from the shared loader validation path.

## Validation performed

- `.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py`
- `.venv/bin/pytest -q tests/test_architecture_baseline_docs.py`

## Deduplication / centralization decisions

- Reused `write_workflow_json(...)` for locality and JSON path enforcement instead of adding a second filesystem guard.
- Reused the shared loader resolution/coercion surfaces instead of adding a second workflow-parameter validator.
