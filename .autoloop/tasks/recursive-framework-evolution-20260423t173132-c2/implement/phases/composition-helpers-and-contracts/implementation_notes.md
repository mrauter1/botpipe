# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t173132-c2
- Pair: implement
- Phase ID: composition-helpers-and-contracts
- Phase Directory Key: composition-helpers-and-contracts
- Phase Title: Add Composition Authoring Helpers
- Scope: phase-local producer artifact

## Files changed

- `stdlib/composition.py`
- `stdlib/__init__.py`
- `docs/authoring.md`
- `tests/unit/test_stdlib_and_extensions.py`
- `tests/runtime/test_workspace_and_context.py`
- `tests/test_architecture_baseline_docs.py`
- `.autoloop/tasks/recursive-framework-evolution-20260423t173132-c2/decisions.txt`

## Symbols touched

- `run_child_workflow`
- `adopt_child_artifacts`
- `stdlib.__all__`
- `_build_lifecycle_context`
- `_build_child_result`
- `_capture_child_invocation`
- `_write_parent_composition_helper_workflow_package`

## Checklist mapping

- Milestone 1: complete
  - added the pure-authoring composition helper module
  - exported the helper seam through `stdlib/__init__.py`
  - documented the boundary in `docs/authoring.md`
  - added unit/runtime/doc coverage for additive composition behavior
- Milestones 2 and 3: intentionally not touched in this phase-local run

## Assumptions

- Repo-root `core/`, `runtime/`, `stdlib/`, and `workflows/` are the authoritative implementation surface for this cycle.
- The active phase contract limits this run to the composition-helper framework improvement, not the new workflow package or recursive memory updates.

## Preserved invariants

- Runtime-owned control surfaces remain limited to `expected_output_schema`, `available_routes`, and `route_contracts`.
- Existing `ctx.invoke_workflow(...)` child-run semantics, metadata recording, and child-workspace isolation remain unchanged.
- No new runtime/core step types, CLI flags, persisted run metadata fields, or provider/session payload shapes were introduced.
- Shipped release and incident workflows were not migrated.

## Intended behavior changes

- Added an optional stdlib composition seam for explicit child-workflow invocation and parent-local artifact adoption.
- Added authoring guidance and tests that lock the helper boundary to authoring-only behavior.

## Known non-changes

- No `SubworkflowStep` or other runtime-managed composition primitive.
- No changes to `runtime/runner.py`, session persistence, or child-run metadata shape.
- No workflow-package authoring for `investigation_request_to_evidence_pack` in this phase.

## Expected side effects

- Workflow authors can now copy selected child artifacts into `ctx.workflow_folder` without reimplementing copy/validation logic.
- Parent workflows remain responsible for selecting adopted artifacts and target paths explicitly.

## Validation performed

- `.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py` -> `15 passed`
- `.venv/bin/pytest -q tests/runtime/test_workspace_and_context.py` -> `8 passed`
- `.venv/bin/pytest -q tests/test_architecture_baseline_docs.py` -> `8 passed`

## Deduplication / centralization decisions

- Centralized child-artifact adoption path validation and copy behavior in `stdlib/composition.py` instead of repeating it inside each parent workflow.
- Kept child-workflow execution delegated to `ctx.invoke_workflow(...)` so runtime child-run logic stays single-sourced.
