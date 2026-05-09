# Original intent considered

The request asked for internal complexity reduction across the ten listed hotspots, with no compatibility shims and with behavior preserved through focused parity tests. The requested scope covered:

- Provider-policy translators: `CodexPolicyEmitter._build_config_payload`, `ClaudePolicyEmitter._build_settings_payload`, and `_policy_layer_to_override`
- Authoring/builder reducers: `_validate_simple_prompt_reference`, `collect_artifact_inventory`, `compiled_step_from_step_plan`, and `render_branch_group_context`
- Runtime/discovery extraction: `Engine.run_async` and `describe_workflow_class`
- Conditional cleanup: `_capability_entry_from_resolved` only if adjacent work already opened `botlane/core/workflow_capabilities.py`

The request also explicitly called for exact-output or exact-error regression gates around provider emitters, policy override lowering, artifact inventory, placeholder validation, and engine loop behavior.

# Clarifications / superseding decisions

- `botlane/*` was treated as the refactor source of truth; no `build/lib/*` compatibility mirroring was required.
- `botlane/core/placeholders.py` remained the single shared simple-prompt validator implementation, with `botlane/core/discovery.py` kept as a thin wrapper to avoid wording drift.
- `Engine.run_async` and `describe_workflow_class` were intentionally sequenced after provider/policy and authoring/builder work because they carried the highest regression risk.
- Hotspot 9 was explicitly deferred unless adjacent source changes already opened `botlane/core/workflow_capabilities.py`; later implementation and test turns preserved that deferment instead of broadening scope.
- Runtime/discovery test scope intentionally reused the existing engine contract suite for `goto` checkpoint sequencing and terminal hook parity instead of duplicating a larger harness.

# Implemented behavior

Live source and tests match the requested refactor shape:

- Provider-policy helpers are extracted and coordinator-style in `botlane/runtime/providers/codex_policy.py`, `botlane/runtime/providers/claude_policy.py`, and `botlane/policy.py`.
- Placeholder-root dispatch is table-driven in `botlane/core/placeholders.py`.
- Artifact registration is builder-based in `botlane/core/inventory.py`.
- Branch-group presentation is split into section renderers in `botlane/core/branch_groups/manifest.py`.
- Runtime loop state and workflow discovery are extracted into private phases in `botlane/core/engine.py` and `botlane/core/discovery.py`, including `_RunLoopState` and `WorkflowNamespaceScan`.
- `botlane/core/workflow_capabilities.py::_capability_entry_from_resolved` remains unchanged, consistent with the explicit deferment rule.

Current audit-time validation passed:

- `.venv/bin/python -m pytest tests/runtime/test_provider_policy_emitters.py tests/unit/test_policy.py tests/unit/test_simple_policy.py tests/runtime/test_provider_policy_config.py -q`
  Result: `77 passed`
- `.venv/bin/python -m pytest tests/unit/test_placeholder_refs.py tests/unit/test_simple_surface.py tests/unit/test_inventory.py tests/unit/test_step_plans.py tests/unit/test_route_contracts.py tests/contract/test_branch_result_serialization.py -q`
  Result: `117 passed`
- `.venv/bin/python -m pytest tests/unit/test_runtime_and_discovery_extraction.py -q`
  Result: `7 passed`
- `.venv/bin/python -m pytest tests/contract/engine/test_runtime_controls.py -q`
  Result: `16 passed`
- `.venv/bin/python -m pytest tests/runtime/test_workflow_reference_resolution.py -k 'inspect_workflow_reference or capability_inspection or simple_declaration_workflow_is_discoverable_by_path_module_name_and_capability_inspection' -q`
  Result: `1 passed, 13 deselected`
- Combined cross-phase audit batch:
  `.venv/bin/python -m pytest tests/runtime/test_provider_policy_emitters.py tests/unit/test_policy.py tests/unit/test_simple_policy.py tests/runtime/test_provider_policy_config.py tests/unit/test_placeholder_refs.py tests/unit/test_simple_surface.py tests/unit/test_inventory.py tests/unit/test_step_plans.py tests/unit/test_route_contracts.py tests/contract/test_branch_result_serialization.py tests/unit/test_runtime_and_discovery_extraction.py tests/contract/engine/test_runtime_controls.py -q`
  Result: `217 passed`

# Unresolved gaps

No material unresolved gaps were found.

# Differences justified by later clarification or analysis

- Hotspot 9 was not refactored because the activation condition never occurred: `botlane/core/workflow_capabilities.py` was not opened by adjacent source work in this run. That behavior matches the later plan correction and implementation/test decisions, so it is an explicit deferment, not a silent omission.
- `botlane/core/discovery.py` did not gain a second placeholder-dispatch implementation. Keeping it as a thin wrapper over `botlane/core/placeholders.py` was an explicit anti-drift decision.
- The runtime/discovery phase did not duplicate the broader engine contract harness for `goto` and terminal hook sequencing. Reusing `tests/contract/engine/test_runtime_controls.py` was an explicit later test-scoping decision and the reused suite now passes.

# Recommended next run

No follow-up implementation run is required for this request.
