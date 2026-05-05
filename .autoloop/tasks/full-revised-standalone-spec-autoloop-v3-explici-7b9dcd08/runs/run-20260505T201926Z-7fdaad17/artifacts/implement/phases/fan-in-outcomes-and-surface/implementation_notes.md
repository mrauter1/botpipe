# Implementation Notes

- Task ID: full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08
- Pair: implement
- Phase ID: fan-in-outcomes-and-surface
- Phase Directory Key: fan-in-outcomes-and-surface
- Phase Title: Fan-In, Outcomes, Surface
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/branch_groups/context.py`
- `autoloop/core/branch_groups/runtime.py`
- `autoloop/core/branch_groups/manifest.py`
- `autoloop/runtime/static_graph.py`
- `decisions.txt`

## Symbols touched
- `create_fan_in_context`
- `BranchGroupRuntime._run_fan_in`
- `BranchGroupRuntime._run_branches`
- `render_branch_group_context`
- `branch_error_summary`
- `_branch_group_surface_payload`
- `_branch_group_outcome_payload`

## Checklist mapping
- Capture/fan-in orchestration: preserved composite capture/finalize behavior and added deterministic fan-in execution ids plus fan-in runtime event attribution.
- Manifest/context shape: expanded branch-group markdown summaries with declaration-order failure, needs-input, and cancellation details while preserving deterministic branch ordering.
- Static graph/topology surface: added additive branch-group outcome-policy and chain-route metadata without changing existing route payload shapes.
- Checkpoint/resume contract: no behavioral change; composite-boundary checkpoint/resume semantics remain unchanged.

## Assumptions
- Additive observability/topology fields are safe for existing readers because they do not replace or rename current keys.
- Fan-in nested execution ids should follow ordinary step-id formatting (`<step>:<visit>`) rather than reuse the composite branch-group execution id.

## Preserved invariants
- Branch route capture still skips `on_taken` hooks and does not follow branch destinations.
- Fan-in still finalizes exactly once through the composite route table.
- Branch-group evidence remains rooted under `{workflow_folder}/_branch_groups/...`.
- Manifest branch ordering remains declaration-stable.
- Composite-boundary checkpoint/resume behavior remains unchanged; no branch-specific resume was added.

## Intended behavior changes
- Fan-in runtime events and nested provider/hook traces now carry a deterministic fan-in step execution id.
- `branch_scheduled` runtime events now include the composite execution id.
- Static graph/topology branch-group payloads now expose `outcome_policy`, `has_fan_in`, `default_chain_route`, and `rework_chain_route`.
- Branch-group `context.md` now includes detail lines for failed, needs-input, cancelled, and skipped branches instead of count-only summaries.

## Known non-changes
- No changes to mechanical outcome routing semantics.
- No changes to checkpoint payload structure or resume targeting.
- No changes to branch manifest JSON schema keys beyond existing runtime output.

## Expected side effects
- Runtime trace consumers can attribute fan-in events more precisely.
- Static-graph/topology consumers receive additive branch-group metadata for branch-group outcome inspection.
- Human-readable branch-group context summaries are more informative for fan-in/downstream review.

## Validation performed
- `.venv/bin/python -m pytest -q tests/contract/test_branch_group_runtime.py tests/runtime/test_runtime_static_graph.py tests/runtime/test_runtime_tracing.py tests/unit/test_branch_group_context_sessions.py tests/strictness/test_no_compat.py`
  - Result: `76 passed`

## Deduplication / centralization
- Kept branch-group surface serialization centralized in `autoloop/runtime/static_graph.py`.
- Kept branch-group summary rendering centralized in `autoloop/core/branch_groups/manifest.py` rather than duplicating per-surface summary logic.
