# Implementation Notes

- Task ID: autoloop-v3-explicit-branch-groups-full-revised-76d1507c
- Pair: implement
- Phase ID: composite-runtime-and-evidence
- Phase Directory Key: composite-runtime-and-evidence
- Phase Title: Composite Runtime And Evidence
- Scope: phase-local producer artifact

## Files Changed
- `autoloop/core/branch_groups/manifest.py`
- `autoloop/core/branch_groups/outcomes.py`
- `autoloop/core/branch_groups/runtime.py`
- `autoloop/core/branch_groups/context.py`
- `autoloop/core/branch_groups/__init__.py`
- `autoloop/core/compiler.py`
- `autoloop/core/discovery.py`
- `autoloop/core/engine.py`
- `autoloop/core/engine_collaborators.py`
- `autoloop/core/artifacts.py`
- `autoloop/core/operations.py`
- `autoloop/core/inventory.py`
- `tests/contract/test_branch_group_runtime.py`

## Symbols Touched
- `BranchGroupRuntime`
- `build_branch_manifest`
- `render_branch_group_context`
- `select_branch_group_outcome`
- `StateCell`
- `CompiledStep.route_table`
- `_compile_branch_group_internal_steps`
- `_compile_branch_group_internal_step`
- `_compile_sessions`
- `_compiled_step_session_name`
- `collect_artifact_inventory`
- `StepDispatcher.execute`
- `Engine._route_table_for_step`
- `Engine._compiled_route_for_step`
- `resolve_artifact_template`
- `render_runtime_template`

## Checklist Mapping
- Plan milestone 3 / dedicated runtime subsystem:
  - Added `branch_groups/runtime.py`, `manifest.py`, and `outcomes.py`.
- Plan milestone 3 / dispatcher and minimal engine wiring:
  - Added `Engine.branch_group_runtime` and dispatched `branch_group` steps through it.
- Plan milestone 3 / branch scheduling and settlement:
  - Implemented bounded thread-based scheduling with `concurrency`, `all`, and `fail_fast` handling.
- Plan milestone 3 / ordered branch-result capture:
  - Reused `StepDispatcher.execute()` for branch/fan-in execution and persisted declaration-order manifests.
- Plan milestone 3 / evidence contract:
  - Wrote `_branch_groups/<group>/results.json` and `context.md` with deterministic summaries and per-branch results.
- Plan milestone 3 / fan-in and mechanical outcomes:
  - Routed through fan-in when present and implemented `all_done`, `all_settled`, `any_done`, and callable custom aggregators otherwise.
- Plan milestone 4 dependency needed by this slice / runtime placeholders and artifact rooting:
  - Added runtime `branch.*` / `fan_in.*` placeholder resolution and fixed relative templated artifact rooting under the owning step directory.

## Assumptions
- V1 `fail_fast` treats a branch `status="failed"` result as the cancellation trigger for unscheduled sibling branches.
- Nested branch/fan-in steps should keep their own local route tables rather than mutating the parent compiled workflow route map.
- Inline explicit step sessions may be unnamed by authors; deterministic synthetic slot names are acceptable compiler-owned lowering so long as branch-session freshness validation still happens on the authored `Session` object.

## Preserved Invariants
- `Engine.run()` remains the only owner of top-level cursor advancement and checkpoint persistence.
- Branch and fan-in steps still execute through the ordinary single-step engine path, including hooks, provider calls, artifact validation, and route finalization.
- Parent session-store activation remains unchanged after branch completion; branch-created provider sessions stay inside `BranchSessionStoreView`.
- Ordinary non-branch workflows keep their existing compile-time route tables and default-session behavior.

## Intended Behavior Changes
- Branch-group steps now execute as composite barriers that emit runtime-owned evidence under `_branch_groups/<group>/...`.
- No-fan-in composites now route mechanically from persisted branch results instead of exposing placeholder-only compiled metadata.
- Fan-in steps now receive resolved `ctx.fan_in` metadata plus `FanIn.results()` / `FanIn.context()` workspace reads at runtime.
- Inline explicit step sessions now open concrete provider bindings even when the author did not bind the `Session` object to a workflow attribute.

## Known Non-Changes
- No partial branch resume or branch-specific checkpoint schema was added.
- No workspace isolation, conflict detection, artifact merge, or shared-state merge logic was added.
- Child workflow branch steps and child workflow fan-in remain unsupported in v1.

## Expected Side Effects
- Branch-group execution now produces runtime event payloads for branch scheduling/completion and manifest writing.
- Nested branch-group artifact declarations now participate in the normal compiled artifact inventory so branch writes can be resolved and validated like ordinary step artifacts.
- Equivalent fan-out branch artifacts that originate from repeated lowering of the same authored step now share one compiled artifact identity.

## Validation Performed
- `.venv/bin/python -m pytest -q tests/contract/test_branch_group_runtime.py`
- `.venv/bin/python -m pytest -q tests/unit/test_simple_surface.py -k 'branch_group or fan_in or provider_backed_branch'`
- `.venv/bin/python -m pytest -q tests/unit/test_branch_group_context_sessions.py`
- `.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py -k 'provider_steps_without_explicit_session_use_default_session or declared_session_auto_opens_without_on_start or on_start_opens_sessions_before_execution or llm_step_contract_logs_outcome_raw_output_and_uses_global_route'`

## Deduplication / Centralization
- Local nested-step route execution is centralized in compiler-produced `CompiledStep.route_table` plus engine route lookup helpers rather than a second branch-only executor.
- Mechanical outcome routing is centralized in `branch_groups/outcomes.py`.
- Evidence rendering is centralized in `branch_groups/manifest.py`.
