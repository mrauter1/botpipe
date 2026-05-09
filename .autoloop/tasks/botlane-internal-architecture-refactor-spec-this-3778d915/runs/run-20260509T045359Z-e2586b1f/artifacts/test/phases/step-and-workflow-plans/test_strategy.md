# Test Strategy

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: test
- Phase ID: step-and-workflow-plans
- Phase Directory Key: step-and-workflow-plans
- Phase Title: Step And Workflow Plans
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- Typed step-plan lowering by compiled kind:
  Covered in `tests/unit/test_step_plans.py::test_step_plans_cover_prompt_pair_python_and_child_variants`
  Checks prompt, produce/verify, python, and child-workflow plans lower to the expected variant types and preserve authored-step identity on `StepHeader.original_step`.
- Branch-group typed plan shape and helper IO lowering:
  Covered in `tests/unit/test_step_plans.py::test_branch_group_step_plan_keeps_nested_plan_shapes_and_fan_in_helpers`
  Checks nested branch plans, fan-in helper references, exact compiled round-trip, and rebuild without top-level `_compiled_step`.
- Branch-group parity failure path:
  Covered in `tests/unit/test_step_plans.py::test_branch_group_step_plan_raises_if_nested_parity_metadata_is_missing`
  Checks the adapter raises a clear `ValueError` instead of silently emitting an invalid compiled branch-group step when nested parity metadata is missing.
- WorkflowPlan adapter entrypoint and parity:
  Covered in `tests/unit/test_workflow_plan_adapters.py::test_compile_workflow_plan_returns_internal_workflow_plan_with_topology_hash_parity`
  Checks `compile_workflow_plan(...)` returns `WorkflowPlan` and preserves topology hash and core workflow metadata.
- CompiledWorkflow round-trip parity:
  Covered in `tests/unit/test_workflow_plan_adapters.py::test_workflow_plan_adapter_round_trip_preserves_compiled_workflow_shape`
  Checks compiled workflow equality, topology hash parity, and artifact inventory parity.
- Route-table parity:
  Covered in `tests/unit/test_workflow_plan_adapters.py::test_workflow_plan_routes_match_compiled_route_tables_and_globals`
  Checks route tags, targets, visibility, schemas, handoff, disabled/runtime-control status, and required writes.
- Logical immutability of copied maps:
  Covered in `tests/unit/test_workflow_plan_adapters.py::test_workflow_plan_adapters_copy_maps_instead_of_reusing_mutable_compiled_dicts`
  Checks plan maps stay stable when compiled or rebuilt workflow dictionaries are mutated.

## Preserved Invariants Checked

- `compile_workflow(...)` remains the compatibility path and its outputs still compare equal after plan round-trips.
- `WorkflowPlan.routes` remains the canonical route table source; `StepHeader` does not expose legacy route tuple fields.
- Branch-group round-trip parity can rebuild from explicit nested parity carriers without depending on `StepHeader.original_step`.

## Edge Cases And Failure Paths

- Top-level branch-group parity carrier removed: covered and expected to still round-trip.
- Nested branch parity carrier removed during branch-group reconstruction: covered and expected to fail loudly with a stable error substring.

## Flake Risk / Stabilization

- No timing, network, or filesystem nondeterminism added.
- Coverage stays on compile-time pure functions and deterministic dataclass transforms.

## Known Gaps

- Full-suite runtime execution remains out of scope for this test turn; coverage here is focused on adapter-layer invariants and regression-prone plan conversions.
