Fix the runtime/context contract drift left exposed by the runtime/discovery extraction.

Preserve the current refactor structure, but make the executable runtime use one consistent mutator surface across `Context`, `ExecutionFrame`, engine collaborators, worklist helpers, and branch-group context helpers so preserved engine behavior works again. The follow-up must clear the current failures in:

- `tests/unit/test_simple_surface.py`
- `tests/unit/test_runtime_and_discovery_extraction.py`
- `tests/contract/engine/test_runtime_controls.py`

Use the combined regression batch below as the acceptance command:

`.venv/bin/python -m pytest tests/runtime/test_provider_policy_emitters.py tests/unit/test_policy.py tests/unit/test_simple_policy.py tests/runtime/test_provider_policy_config.py tests/unit/test_placeholder_refs.py tests/unit/test_simple_surface.py tests/unit/test_inventory.py tests/unit/test_step_plans.py tests/unit/test_route_contracts.py tests/contract/test_branch_result_serialization.py tests/unit/test_runtime_and_discovery_extraction.py tests/contract/engine/test_runtime_controls.py -q`

Keep hotspot 9 deferred unless adjacent source work actually opens `botlane/core/workflow_capabilities.py`.
