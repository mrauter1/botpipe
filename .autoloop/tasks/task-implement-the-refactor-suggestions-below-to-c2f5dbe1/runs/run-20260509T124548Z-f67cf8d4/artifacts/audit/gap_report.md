# Original intent considered

The request asked for internal complexity reduction across the ten listed hotspots, with no compatibility shims and with behavior preserved through focused parity tests. The requested scope covered:

- Provider-policy translators: `CodexPolicyEmitter._build_config_payload`, `ClaudePolicyEmitter._build_settings_payload`, and `_policy_layer_to_override`
- Authoring/builder reducers: `_validate_simple_prompt_reference`, `collect_artifact_inventory`, `compiled_step_from_step_plan`, and `render_branch_group_context`
- Runtime/discovery extraction: `Engine.run_async` and `describe_workflow_class`
- Conditional cleanup: `_capability_entry_from_resolved` only if adjacent work already opened `botlane/core/workflow_capabilities.py`

The request also explicitly called for exact-output or exact-error regression gates around provider emitters, policy override lowering, artifact inventory, placeholder validation, and engine loop behavior.

# Clarifications / superseding decisions

- `botlane/*` remained the refactor source of truth; no `build/lib/*` mirroring was required.
- `botlane/core/placeholders.py` remained the shared simple-prompt validator implementation, with `botlane/core/discovery.py` kept thin to avoid wording drift.
- `Engine.run_async` and `describe_workflow_class` were intentionally sequenced after provider/policy and authoring/builder phases because they were the highest-risk extractions.
- Hotspot 9 was explicitly deferred unless adjacent work already opened `botlane/core/workflow_capabilities.py`.
- The runtime/discovery test phase intentionally reused the broader runtime-control contract suite instead of cloning a second harness.

# Implemented behavior

Live source still reflects most of the requested refactor shape:

- Provider-policy emitters are helper/coordinator based in `botlane/runtime/providers/codex_policy.py`, `botlane/runtime/providers/claude_policy.py`, and `botlane/policy.py`.
- Placeholder-root dispatch is table-driven in `botlane/core/placeholders.py`.
- Artifact registration is builder-based in `botlane/core/inventory.py`.
- Branch-group context rendering is split into section helpers in `botlane/core/branch_groups/manifest.py`.
- Runtime/discovery extraction is present in `botlane/core/engine.py` and `botlane/core/discovery.py`, including `_RunLoopState` and `WorkflowNamespaceScan`.
- Hotspot 9 remains unchanged in `botlane/core/workflow_capabilities.py`, which is consistent with the explicit deferment rule.

Current audit-time validation evidence is mixed:

- Provider-policy suites currently pass:
  `.venv/bin/python -m pytest tests/runtime/test_provider_policy_emitters.py tests/unit/test_policy.py tests/unit/test_simple_policy.py tests/runtime/test_provider_policy_config.py -q`
  Result: `77 passed`
- The deferred hotspot-9 capability-inspection target currently passes:
  `.venv/bin/python -m pytest tests/runtime/test_workflow_reference_resolution.py -k 'inspect_workflow_reference or capability_inspection or simple_declaration_workflow_is_discoverable_by_path_module_name_and_capability_inspection' -q`
  Result: `1 passed, 13 deselected`
- The exact combined cross-phase audit batch cited by the previous audit does not currently pass:
  `.venv/bin/python -m pytest tests/runtime/test_provider_policy_emitters.py tests/unit/test_policy.py tests/unit/test_simple_policy.py tests/runtime/test_provider_policy_config.py tests/unit/test_placeholder_refs.py tests/unit/test_simple_surface.py tests/unit/test_inventory.py tests/unit/test_step_plans.py tests/unit/test_route_contracts.py tests/contract/test_branch_result_serialization.py tests/unit/test_runtime_and_discovery_extraction.py tests/contract/engine/test_runtime_controls.py -q`
  Result: `24 failed, 193 passed`

# Unresolved gaps

- The runtime/discovery refactor is not fully behavior-preserving in the executable final tree. The current combined regression batch fails across `tests/unit/test_simple_surface.py`, `tests/unit/test_runtime_and_discovery_extraction.py`, and `tests/contract/engine/test_runtime_controls.py`.
- The failure shape is a runtime/context contract drift. Live refactor code now routes several mutations through `ExecutionFrame` helpers, for example:
  - `botlane/core/engine_collaborators.py:606-612`
  - `botlane/core/worklists.py:344-345`
  - `botlane/core/branch_groups/context.py:231-232`
  - `botlane/core/execution_frame.py:158,223,226,245`
- However, the executable runtime/test environment still hits code paths that expect legacy context-surface mutators such as `_set_state` and `_cache_worklist_items`, which raises `AttributeError` from `botlane/core/context.py`.
- This is a material unresolved gap because the original request explicitly required runtime behavior preservation and exact regression gates around engine-loop behavior.

# Differences justified by later clarification or analysis

- Hotspot 9 remained deferred because `botlane/core/workflow_capabilities.py` was not opened by adjacent source work in this run. That is an explicit later deferment, not a silent omission.
- `botlane/core/discovery.py` did not gain a second placeholder dispatcher. Keeping placeholder validation centralized in `botlane/core/placeholders.py` was an explicit anti-drift decision.
- Reusing the broader runtime-control contract suite was justified by later test-scoping decisions, but that reused suite now supplies the evidence for the unresolved runtime/context regression rather than supporting a gap-free conclusion.

# Recommended next run

Write a focused follow-up implementation for the runtime/context contract drift exposed by the runtime/discovery extraction. Keep the existing refactor structure, but restore preserved runtime behavior by making the executable runtime use one consistent mutator surface across `Context`, `ExecutionFrame`, engine collaborators, worklist helpers, and branch-group context helpers, then rerun the failing runtime/simple/contract suites.
