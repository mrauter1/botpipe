# Implementation Notes

- Task ID: recursive-framework-evolution-20260424t163807-c7
- Pair: implement
- Phase ID: migrate-refinement-decomposition-callers
- Phase Directory Key: migrate-refinement-decomposition-callers
- Phase Title: Migrate Workflow Callers
- Scope: phase-local producer artifact

## Pre-change audit summary

- Cycle mode for this phase: `consolidate`
- Three most relevant surfaces:
  - `stdlib/candidate_surfaces.py`
  - `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`
  - `workflows/workflow_package_to_composable_building_blocks/workflow.py`
- Repeated mechanics identified:
  - baseline manifest boundary/file/digest validation tails
  - candidate manifest boundary/file/digest validation tails
  - overlay validation result normalization tails
- Simplification chosen:
  - migrate both workflow callers onto the expanded candidate-surface seam and keep only refinement-specific evaluation alignment plus decomposition-specific building-block/evidence rules local
- New workflow necessity:
  - none; this phase is caller consolidation only

## Files changed

- `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`
- `workflows/workflow_package_to_composable_building_blocks/workflow.py`
- `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
- `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- `.autoloop/tasks/recursive-framework-evolution-20260424t163807-c7/decisions.txt`
- `.autoloop/tasks/recursive-framework-evolution-20260424t163807-c7/implement/phases/migrate-refinement-decomposition-callers/implementation_notes.md`

## Symbols touched

- Refinement workflow:
  - `_validate_baseline_manifest(...)`
  - `_validate_candidate_manifest(...)`
  - `_validate_candidate_overlay(...)`
- Decomposition workflow:
  - `_validate_baseline_parent_manifest(...)`
  - `_validate_candidate_decomposition_manifest(...)`
  - `_validate_candidate_overlay(...)`
- Runtime tests:
  - added one publish-time baseline-manifest boundary rejection test per workflow

## Checklist mapping

- Plan phase `migrate-refinement-decomposition-callers` AC-1:
  - replaced refinement/decomposition workflow-local baseline and candidate manifest validator tails with calls to `validate_baseline_surface_manifest(...)` and `validate_candidate_surface_manifest(...)`
  - replaced both workflow-local overlay normalization tails with `normalize_candidate_surface_overlay_result(...)`
- Plan phase `migrate-refinement-decomposition-callers` AC-2:
  - kept targeted runtime proof green for unchanged receipts, boundary rejections, and overlay behavior
  - added explicit runtime coverage that shared-seam baseline-boundary mismatches still fail publication in both workflows

## Assumptions

- This phase should preserve current artifact names, receipt payload keys, prompt paths, and route grammar exactly.
- Global cycle docs and recursive memory files remain out of phase scope for this producer run; no out-of-phase memory updates were made here.

## Preserved invariants

- No CLI, runtime/provider boundary, `ctx.invoke_workflow(...)`, or `workflow.toml` contract change
- No prompt role/path or route-grammar change
- No receipt key or publication artifact filename change
- Refinement keeps evaluation-summary and capability/authoring-surface checks local
- Decomposition keeps evidence capture, building-block index validation, and declared doc/runtime-test presence checks local

## Intended behavior changes

- None at the workflow contract level; this phase only consolidates duplicated publish-time validation mechanics onto the shared stdlib seam

## Known non-changes

- `docs/architecture.md` and `docs/authoring.md` unchanged
- `.autoloop_recursive/*` memory ledgers unchanged in this phase-local run
- No new helpers or workflows added outside the existing candidate-surface seam

## Expected side effects

- Refinement and decomposition publication paths now share the same baseline/candidate manifest validator implementation and overlay normalization surface
- The refinement caller preserves its legacy boundary error wording by translating the shared seam's generic allowed-boundary rejection

## Validation performed

- `./.venv/bin/python -m py_compile workflows/workflow_and_eval_to_refined_workflow_package/workflow.py workflows/workflow_package_to_composable_building_blocks/workflow.py`
- `./.venv/bin/pytest -q tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
- `./.venv/bin/pytest -q tests/runtime/test_workflow_package_to_composable_building_blocks.py`

## Deduplication / centralization decisions

- Centralized baseline manifest boundary/file/digest validation in `stdlib/candidate_surfaces.py`
- Centralized candidate manifest boundary/file/digest validation in `stdlib/candidate_surfaces.py`
- Centralized overlay-result normalization in `stdlib/candidate_surfaces.py`
- Kept decomposition-only building-block policy and refinement-only publication semantics workflow-local by design
