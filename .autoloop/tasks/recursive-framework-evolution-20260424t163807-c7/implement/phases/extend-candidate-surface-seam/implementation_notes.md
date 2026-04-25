# Implementation Notes

- Task ID: recursive-framework-evolution-20260424t163807-c7
- Pair: implement
- Phase ID: extend-candidate-surface-seam
- Phase Directory Key: extend-candidate-surface-seam
- Phase Title: Extend Candidate Surface Seam
- Scope: phase-local producer artifact

## Files changed

- `stdlib/candidate_surfaces.py`
- `stdlib/__init__.py`
- `tests/unit/test_stdlib_and_extensions.py`
- `.autoloop/tasks/recursive-framework-evolution-20260424t163807-c7/decisions.txt`

## Symbols touched

- Added `validate_baseline_surface_manifest(...)`
- Added `validate_candidate_surface_manifest(...)`
- Added `normalize_candidate_surface_overlay_result(...)`
- Added internal `_validate_manifest_boundary_fields(...)`
- Updated stdlib re-exports and candidate-surface unit coverage

## Checklist mapping

- Plan phase `extend-candidate-surface-seam` AC-1:
  - extended `stdlib/candidate_surfaces.py` so the shared seam now owns reusable baseline/candidate manifest validation mechanics plus overlay-result normalization
- Plan phase `extend-candidate-surface-seam` AC-2:
  - added focused unit coverage for baseline boundary checks, candidate boundary checks, digest consistency, stdlib re-exports, and overlay-result normalization

## Assumptions

- Workflow-caller migrations remain deferred to the next planned phase; this phase only extends and proves the shared seam.
- Optional exact-path allowances may be absent; the new candidate validator therefore ignores `None` exact-path entries instead of forcing callers to pre-filter them.

## Preserved invariants

- No CLI, runtime, provider, prompt-path, `workflow.toml`, or `ctx.invoke_workflow(...)` contract change
- No refinement evaluation policy or decomposition building-block policy moved into stdlib
- Existing `validate_candidate_surface_overlay(...)` execution semantics unchanged

## Intended behavior changes

- Added reusable stdlib validation/normalization helpers only; no workflow behavior changed in this phase because callers were not migrated yet

## Known non-changes

- `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py` unchanged
- `workflows/workflow_package_to_composable_building_blocks/workflow.py` unchanged
- `docs/authoring.md` and `.autoloop_recursive/*` memory files unchanged in this phase; those remain for the proof/docs/closeout phase

## Expected side effects

- Later workflow migrations can replace duplicated manifest and overlay-result helper tails with the shared seam without widening runtime-owned behavior

## Validation performed

- `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py -k 'candidate_surface_helpers'`
- `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py`

## Deduplication / centralization decisions

- Centralized boundary-field comparison, baseline manifest file-entry validation, candidate manifest file-entry validation, and overlay-result normalization in `stdlib/candidate_surfaces.py`
- Kept building-block index validation, evidence capture, evaluation-summary checks, and receipt shaping workflow-local by design
