# Test Strategy

- Task ID: autoloop-v3-explicit-branch-groups-full-revised-76d1507c
- Pair: test
- Phase ID: authoring-and-compile-model
- Phase Directory Key: authoring-and-compile-model
- Phase Title: Authoring And Compile Model
- Scope: phase-local producer artifact

## Behavior-To-Test Coverage Map

- AC-1 composite compile shape:
  - `test_parallel_branch_group_compiles_as_one_external_step_with_ordered_internal_specs`
  - `test_parallel_branch_group_propagates_explicit_fan_in_routes_to_outer_routes`
  - `test_parallel_branch_group_without_fan_in_materializes_mechanical_outcome_routes`
  - `test_fan_out_branch_group_preserves_branch_inputs_and_order`
- AC-2 branch-only provider session tightening:
  - `test_provider_backed_branch_steps_require_explicit_fresh_sessions_only_inside_branch_groups`
  - `test_branch_group_rejects_non_fresh_verifier_sessions_inside_branch_groups`
- AC-3 fan-in step-kind matrix:
  - `test_branch_group_fan_in_accepts_supported_step_kinds`
  - `test_branch_group_rejects_child_workflow_fan_in_and_non_serializable_fan_out_inputs`

## Preserved Invariants Checked

- Non-branch provider steps still compile with the existing default session behavior.
- Branch groups remain one external compiled step rather than emitting nested authored steps as top-level workflow nodes.
- No-`fan_in` branch groups keep `question` / `failed` control routes while now materializing `done` / `partial` destinations.

## Edge Cases

- `fan_out(...)` preserves declared branch order and per-branch JSON inputs.
- Unsafe branch-group and branch names fail before compilation completes.
- Fan-in-only helper reads and fan-in placeholders are rejected outside fan-in contexts.

## Failure Paths

- Missing branch `Session.fresh()` and non-fresh branch sessions fail compilation.
- Non-fresh `verifier_session` on produce/verify branch steps fails compilation.
- Non-serializable `fan_out(...)` branch payloads fail compilation.
- Child-workflow fan-in remains rejected in v1.

## Flake Risk / Stabilization

- All added coverage is compile-time only and uses inline workflow declarations; no network, timing, filesystem ordering, or provider nondeterminism is involved.

## Known Gaps

- Runtime branch scheduling, manifest/context generation, mechanical outcome execution, and fan-in execution remain out of scope for this phase and therefore are not covered here.
