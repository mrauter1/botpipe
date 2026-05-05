# Implementation Notes

- Task ID: goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6
- Pair: implement
- Phase ID: reconcile-optimizer-source-contracts
- Phase Directory Key: reconcile-optimizer-source-contracts
- Phase Title: Reconcile Optimizer Source Contracts
- Scope: phase-local producer artifact

## Files Changed
- `autoloop_optimizer/optimization.py`
- `decisions.txt`

## Symbols Touched
- `write_selected_workflow_source_manifest`
- `_validate_runtime_observability_schema`
- `_canonical_selected_workflow_manifest_dir`
- `_first_party_workflow_source_dir`

## Checklist Mapping
- Plan item 2.a observability bundle schema migration and validation behavior: completed in `autoloop_optimizer/optimization.py`.
- Plan item 2.b trace-corpus eligible-run preservation and runtime-control observation capture: validated via `tests/unit/test_optimization_helpers.py`; no additional code change required after schema migration fix.
- Plan item 2.c canonical selected-workflow source manifest / mutation validation: completed in `autoloop_optimizer/optimization.py`.
- Plan item 3 packaged-workflow compile/runtime regressions: intentionally deferred; targeted runtime suite still fails on missing `blocked` / `failed` routes and missing framework artifacts.

## Assumptions
- For first-party packaged workflows, optimizer publication should treat `autoloop/workflows/<workflow_name>` as the authoritative package surface even when runtime resolution loaded a repo-local `workflows/<workflow_name>` copy.
- Supported legacy runtime observability payloads are only the schemaless variants of the existing v1 files; explicit alternate schema IDs remain invalid.

## Preserved Invariants
- Worklist selector and progress-board changes were not touched.
- Repo-local `workflows/` execution support remains intact; this phase only normalizes optimizer publication/manifests.
- Explicit unsupported runtime schema IDs still fail validation.

## Intended Behavior Changes
- `load_run_observability_bundle()` now accepts schemaless legacy Plan-1 runtime observability payloads by in-memory migration.
- Selected-workflow source manifests now hash one canonical first-party package surface and keep mutation checks on that same surface.

## Known Non-Changes
- No workflow-local route declarations were edited.
- No framework artifact resolution logic was changed.
- No downstream packaged-workflow validators were changed in this phase.

## Expected Side Effects
- In temp repos that only copy first-party workflows under `workflows/`, manifest generation may materialize `autoloop/workflows/<workflow_name>` before hashing so downstream publication checks see the canonical package surface.

## Validation Performed
- Passed: `tests/unit/test_optimization_helpers.py`
- Investigated but deferred as out-of-phase/downstream: `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py`
  - Remaining failures are packaged-workflow/runtime contract issues: missing `blocked` / `failed` routes and missing `framework_architecture_doc`.

## Deduplication / Centralization
- Reused the shared schema-registry migrator path from runtime readers instead of adding optimizer-local compatibility parsing.
- Centralized canonical selected-workflow manifest path selection in `autoloop_optimizer/optimization.py` so manifest writing and mutation validation share the same surface contract.
