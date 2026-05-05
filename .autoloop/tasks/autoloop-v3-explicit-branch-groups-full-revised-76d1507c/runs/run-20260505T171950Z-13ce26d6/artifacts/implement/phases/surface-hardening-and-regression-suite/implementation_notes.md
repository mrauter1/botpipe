# Implementation Notes

- Task ID: autoloop-v3-explicit-branch-groups-full-revised-76d1507c
- Pair: implement
- Phase ID: surface-hardening-and-regression-suite
- Phase Directory Key: surface-hardening-and-regression-suite
- Phase Title: Surface Hardening And Regression Suite
- Scope: phase-local producer artifact

## Files Changed
- `autoloop/core/compiler.py`
- `autoloop/core/branch_groups/runtime.py`
- `autoloop/runtime/static_graph.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/runtime/test_runtime_static_graph.py`
- `tests/runtime/test_runtime_tracing.py`

## Symbols Touched
- `_topology_hash_payload`, `_topology_hash_step_payload`, `_topology_hash_branch_group_payload`
- `BranchGroupRuntime.run`, `_run_branches`, `_execute_branch`, `_run_fan_in`
- `workflow_static_step_graph_payload`, `workflow_topology_payload`
- `_branch_group_surface_payload`, `_internal_step_surface_payload`, `_internal_route_payload`, `_runtime_control_hook_locations`

## Checklist Mapping
- Milestone 4 / placeholder-rooting hardening: added branch/fan-in artifact-template rooting regressions in `tests/unit/test_primitives_and_stores.py`.
- Milestone 4 / static graph and topology metadata: added additive `branch_group` payloads in `autoloop/runtime/static_graph.py`.
- Milestone 4 / topology hashing regression safety: extended `autoloop/core/compiler.py` topology-hash serialization to include branch-group internals.
- Milestone 4 / runtime-event coverage: enriched branch-group runtime event payloads and added filesystem-runner trace coverage in `tests/runtime/test_runtime_tracing.py`.
- Milestone 4 / regression suite: added runtime graph/hash coverage in `tests/runtime/test_runtime_static_graph.py`.

## Assumptions
- Existing compile-time placeholder legality tests in `tests/unit/test_simple_surface.py` remain the authoritative guard for rejecting illegal `{branch.*}` and `{fan_in.*}` usage outside branch/fan-in steps.
- Additive nested metadata on branch-group steps is sufficient; no schema-version churn was introduced for existing non-branch steps.

## Preserved Invariants
- Non-branch workflow graph and trace payloads keep their existing top-level shape.
- Branch-group execution still reuses `StepDispatcher.execute()` and does not move scheduling logic into `engine.py`.
- Relative authored artifact paths continue to root under the owning step directory after placeholder expansion.

## Intended Behavior Changes
- Static graph and topology outputs now surface nested branch-group internals for inspection.
- `topology_hash` now changes when branch/fan-in internal shape changes.
- Branch-group runtime trace events now carry richer step/evidence metadata and emit explicit skipped/cancelled events under `fail_fast`.

## Known Non-Changes
- No checkpoint schema changes.
- No changes to ordinary step route-table, trace, or artifact-resolution behavior outside branch-group paths.
- No new branch-local workspace or state isolation semantics.

## Expected Side Effects
- Persisted topology/static-graph artifacts for branch-group workflows include additive `branch_group` sections.
- Stored topology hashes for branch-group workflows change relative to earlier branch-group revisions because nested internals are now part of the hash surface.

## Validation Performed
- `.venv/bin/pytest -q tests/contract/test_branch_group_runtime.py -q`
- `.venv/bin/pytest -q tests/unit/test_simple_surface.py -q`
- `.venv/bin/pytest -q tests/unit/test_primitives_and_stores.py tests/runtime/test_runtime_static_graph.py tests/runtime/test_runtime_tracing.py -q`

## Deduplication / Centralization
- Centralized branch-group topology-hash serialization in `autoloop/core/compiler.py` so one helper controls nested hash materialization.
- Centralized nested branch-group graph serialization in `autoloop/runtime/static_graph.py` so static graph and topology payloads share the same branch-group surface builder.
