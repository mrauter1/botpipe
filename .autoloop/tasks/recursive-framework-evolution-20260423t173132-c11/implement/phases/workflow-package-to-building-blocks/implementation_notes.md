# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t173132-c11
- Pair: implement
- Phase ID: workflow-package-to-building-blocks
- Phase Directory Key: workflow-package-to-building-blocks
- Phase Title: Implement Decomposition Workflow
- Scope: phase-local producer artifact

## Files changed

- `workflows/workflow_package_to_composable_building_blocks/__init__.py`
- `workflows/workflow_package_to_composable_building_blocks/params.py`
- `workflows/workflow_package_to_composable_building_blocks/contracts.py`
- `workflows/workflow_package_to_composable_building_blocks/workflow.py`
- `workflows/workflow_package_to_composable_building_blocks/workflow.toml`
- `workflows/workflow_package_to_composable_building_blocks/assets/decomposition_package_checklist.md`
- `workflows/workflow_package_to_composable_building_blocks/prompts/README.md`
- `workflows/workflow_package_to_composable_building_blocks/prompts/frame_producer.md`
- `workflows/workflow_package_to_composable_building_blocks/prompts/frame_verifier.md`
- `workflows/workflow_package_to_composable_building_blocks/prompts/design_producer.md`
- `workflows/workflow_package_to_composable_building_blocks/prompts/design_verifier.md`
- `workflows/workflow_package_to_composable_building_blocks/prompts/implement_producer.md`
- `workflows/workflow_package_to_composable_building_blocks/prompts/implement_verifier.md`
- `workflows/workflow_package_to_composable_building_blocks/prompts/evaluate_producer.md`
- `workflows/workflow_package_to_composable_building_blocks/prompts/evaluate_verifier.md`
- `docs/workflows/workflow_package_to_composable_building_blocks.md`
- `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- `.autoloop/tasks/recursive-framework-evolution-20260423t173132-c11/decisions.txt`

## Symbols touched

- `WorkflowPackageToComposableBuildingBlocks`
- `DecompositionRequestFramingPayload`
- `DecompositionPlanPayload`
- `CandidateDecompositionBuildPayload`
- `CandidateDecompositionEvaluationPayload`
- local candidate publication helpers and validation in `workflow_package_to_composable_building_blocks.workflow`
- workflow-specific docs, prompt templates, and runtime proof

## Checklist mapping

- Plan item `Create the new workflow package under workflows/workflow_package_to_composable_building_blocks/`: done
- Plan item `Define parameter model, route contracts, prompt templates, and checklist asset`: done
- Plan item `Keep overlay validation local by default and publish a deterministic manifest`: done
- Plan item `Publish workflow docs and workflow-specific runtime proof`: done
- Plan item `Update recursive memory files for cycle 11`: done

## Assumptions

- The phase-local contract is authoritative: publish a candidate decomposition overlay and receipt without auto-promoting into the authoritative repo.
- The decomposition surface helper shipped in the earlier phase is the correct selected-workflow capture seam for this workflow and should be reused rather than widened again.

## Preserved invariants

- Runtime behavior, CLI contracts, and `workflow.toml` schema remain unchanged.
- The authoritative selected workflow package is never mutated by this workflow.
- Prompt templates remain the provider-facing operational contract; runtime-owned control stays limited to `expected_output_schema`, `available_routes`, and `route_contracts`.

## Intended behavior changes

- The repo now ships `workflow_package_to_composable_building_blocks` as a reusable candidate-only decomposition building block.
- Publish-time validation now rejects hidden execution, selected-workflow identity drift, and candidate files outside the declared repo-relative boundary for this workflow.
- Decomposition evidence capture now records explicit evidence copies or a `request.md` fallback in `decomposition_evidence_manifest.json`.

## Known non-changes

- No auto-promotion of candidate decomposition outputs into the authoritative repo.
- No public CLI changes.
- No refactors of existing workflow packages outside the selected candidate overlay created by the workflow itself.

## Expected side effects

- Operators and later workflows can now turn explicit decomposition pressure into a parent rewrite candidate, extracted building-block packages, migration guidance, and a deterministic receipt.
- Recursive memory now treats the decomposition layer as shipped rather than merely deferred.

## Validation performed

- `python3 -m py_compile workflows/workflow_package_to_composable_building_blocks/workflow.py workflows/workflow_package_to_composable_building_blocks/contracts.py workflows/workflow_package_to_composable_building_blocks/params.py tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- `PYTHONPATH=/home/rauter/autoloop_v3_bkp .venv/bin/pytest -q tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- Result: `20 passed in 5.17s`

## Deduplication / centralization decisions

- Reused the decomposition surface and lifecycle helper seams from `stdlib/` instead of re-implementing selected-workflow capture or bootstrap/receipt boilerplate.
- Kept candidate-manifest and hidden-execution validation local to this workflow rather than extracting another shared helper before duplication was demonstrated.
