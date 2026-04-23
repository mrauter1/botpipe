# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t173132-c3
- Pair: implement
- Phase ID: child-result-contract-helper
- Phase Directory Key: child-result-contract-helper
- Phase Title: Add Child Result Contract Helper
- Scope: phase-local producer artifact

## Files changed

- `stdlib/composition.py`
- `stdlib/__init__.py`
- `docs/authoring.md`
- `tests/unit/test_stdlib_and_extensions.py`
- `tests/test_architecture_baseline_docs.py`

## Symbols touched

- `stdlib.composition.run_child_workflow`
- `stdlib.composition.require_child_workflow_result`
- `stdlib.composition.adopt_child_artifacts`
- `autoloop_v3.stdlib.__all__`

## Checklist mapping

- Milestone 1 helper implementation: complete via `require_child_workflow_result(...)` in `stdlib/composition.py`
- Milestone 1 export wiring: complete via `stdlib/__init__.py`
- Milestone 1 authoring boundary docs: complete via `docs/authoring.md` and doc assertions
- Milestone 1 focused proof: complete via unit coverage in `tests/unit/test_stdlib_and_extensions.py`

## Assumptions

- The planned helper signature in `plan.md` is authoritative for this phase.
- Child terminal-route validation should check `child_result.last_event.tag` rather than the engine terminal enum.

## Preserved invariants

- `ctx.invoke_workflow(...)` remains unchanged; `run_child_workflow(...)` is still a thin passthrough.
- No changes to `ChildWorkflowResult`, persisted child-run metadata, CLI behavior, or runtime-injected control contracts.
- Child `question` and `blocked` routing remains explicit in workflow code.

## Intended behavior changes

- Added an authoring-only validation helper that can require child status, expected last-event route, and required output artifacts before parent-local artifact adoption.

## Known non-changes

- No runtime-owned subworkflow step or automatic child pause/block propagation.
- No changes to artifact adoption semantics beyond optional pre-validation.

## Expected side effects

- Parent workflows can now fail fast with clearer validation errors before copying child artifacts.
- Authoring docs now describe the validation boundary alongside the existing composition helpers.

## Validation performed

- `.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py`
- `.venv/bin/pytest -q tests/test_architecture_baseline_docs.py -k 'authoring_doc or architecture_doc'`
- `.venv/bin/pytest -q tests/runtime/test_workspace_and_context.py -k 'composition_helper or invoke_workflow_accepts_imported_main_workflow_classes_and_records_child_metadata_shape_for_fatal_children or invoke_workflow_by_name_creates_isolated_child_runs_without_inheriting_parent_answers'`

## Deduplication / centralization decisions

- Centralized repeated child-result contract checks in `stdlib/composition.py` instead of duplicating them in each parent workflow.
