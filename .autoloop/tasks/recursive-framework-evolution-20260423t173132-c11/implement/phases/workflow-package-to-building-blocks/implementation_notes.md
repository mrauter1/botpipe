# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t173132-c11
- Pair: implement
- Phase ID: workflow-package-to-building-blocks
- Phase Directory Key: workflow-package-to-building-blocks
- Phase Title: Implement Decomposition Workflow
- Scope: phase-local producer artifact

## Files changed

- `workflows/workflow_package_to_composable_building_blocks/workflow.py`
- `docs/workflows/workflow_package_to_composable_building_blocks.md`
- `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- `.autoloop/tasks/recursive-framework-evolution-20260423t173132-c11/implement/phases/workflow-package-to-building-blocks/implementation_notes.md`
- `.autoloop/tasks/recursive-framework-evolution-20260423t173132-c11/decisions.txt`

## Symbols touched

- `WorkflowPackageToComposableBuildingBlocks`
- `_write_candidate_decomposition_manifest`
- `_validate_candidate_decomposition_manifest`
- `_surface_relative_paths`
- workflow-specific publish-time regression coverage

## Checklist mapping

- Plan item `Create the new workflow package under workflows/workflow_package_to_composable_building_blocks/`: done
- Plan item `Define parameter model, route contracts, prompt templates, and checklist asset`: done
- Plan item `Keep overlay validation local by default and publish a deterministic manifest`: done
- Plan item `Publish workflow docs and workflow-specific runtime proof`: done; added publish-side regressions for hidden candidate files and missing declared doc/test artifacts
- Reviewer finding `IMP-001`: resolved by rescanning `candidate_decomposition_surface/` and rejecting manifest/file-set drift during publication
- Reviewer finding `IMP-002`: resolved by requiring every declared building-block doc/runtime-test path to exist in the candidate overlay before publication

## Assumptions

- The phase-local contract is authoritative: publish a candidate decomposition overlay and receipt without auto-promoting into the authoritative repo.
- The decomposition surface helper shipped in the earlier phase is the correct selected-workflow capture seam for this workflow and should be reused rather than widened again.

## Preserved invariants

- Runtime behavior, CLI contracts, and `workflow.toml` schema remain unchanged.
- The authoritative selected workflow package is never mutated by this workflow.
- Prompt templates remain the provider-facing operational contract; runtime-owned control stays limited to `expected_output_schema`, `available_routes`, and `route_contracts`.

## Intended behavior changes

- The repo now ships `workflow_package_to_composable_building_blocks` as a reusable candidate-only decomposition building block.
- Publish-time validation now rejects hidden execution, selected-workflow identity drift, manifest drift from the actual candidate surface, missing declared building-block docs/tests, and candidate files outside the declared repo-relative boundary for this workflow.
- Decomposition evidence capture now records explicit evidence copies or a `request.md` fallback in `decomposition_evidence_manifest.json`.

## Known non-changes

- No auto-promotion of candidate decomposition outputs into the authoritative repo.
- No public CLI changes.
- No refactors of existing workflow packages outside the selected candidate overlay created by the workflow itself.

## Expected side effects

- Operators and later workflows can now turn explicit decomposition pressure into a parent rewrite candidate, extracted building-block packages, migration guidance, and a deterministic receipt.
- Publication fails earlier when candidate overlays contain hidden files or omit declared building-block docs/tests, even if a narrower test command would otherwise pass.

## Validation performed

- `python3 -m py_compile workflows/workflow_package_to_composable_building_blocks/workflow.py tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- `PYTHONPATH=/home/rauter/autoloop_v3_bkp .venv/bin/pytest -q tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- Result: `22 passed in 6.49s`

## Deduplication / centralization decisions

- Kept publish-time validation local to this workflow rather than extracting another shared helper before duplication was demonstrated.
- Introduced one workflow-local `_surface_relative_paths(...)` helper so manifest generation and publication enforce the same candidate-surface enumeration logic.
