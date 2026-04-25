# Test Strategy

- Task ID: recursive-framework-evolution-20260424t163807-c6
- Pair: test
- Phase ID: refinement-decomposition-migration
- Phase Directory Key: refinement-decomposition-migration
- Phase Title: Workflow Migration
- Scope: phase-local producer artifact

## Behaviors covered

- Refinement workflow runtime suite:
  - successful publication still emits the same baseline/candidate artifacts and receipt payload, including the unchanged single-workflow `overlay_validation` shape
  - publish-time failures still reject evaluation-summary drift, authoring-surface drift, candidate-manifest drift, out-of-boundary candidate files, state mismatch, and authoritative-source drift
- Decomposition workflow runtime suite:
  - successful publication still emits the same baseline/candidate artifacts, building-block index, and receipt payload, including the unchanged multi-workflow `overlay_validation` shape
  - publish-time failures still reject hidden execution, identity drift, out-of-boundary candidate files, unlisted candidate files, missing declared doc/runtime-test files, and authoritative-source drift

## Preserved invariants checked

- Artifact names, route names, and receipt payload shapes stay unchanged after the migration to `stdlib/candidate_surfaces`
- Workflow-local policy still owns refinement evidence validation and decomposition building-block boundary validation
- Publish-time drift errors remain workflow-local in wording even though the mechanical check moved into the shared seam

## Edge cases and failure paths

- Refinement authoritative-source drift now asserts the error includes the repo-relative prompt path
- Decomposition authoritative-source drift now asserts the error includes the repo-relative prompt path
- Existing boundary-rejection tests continue to cover candidate manifests that drift from the allowed repo-relative surface

## Validation run

- `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py` -> `23 passed`
- `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/runtime/test_workflow_package_to_composable_building_blocks.py` -> `24 passed`

## Flake risk / stabilization

- Tests remain deterministic: temporary repo copies, local file mutation inside per-test workspaces, no network calls, and stable sorted path expectations
- Drift assertions mutate only workspace-local authoritative files and do not depend on timing or global state

## Known gaps

- This phase stays on targeted runtime proof only; the shared helper unit suite already covered seam-level path-hardening and overlay mechanics in the earlier dependency phase
