# Test Strategy

- Task ID: implementation-goal-add-a-first-class-provider-p-5e755cae
- Pair: test
- Phase ID: policy-resolution-propagation
- Phase Directory Key: policy-resolution-propagation
- Phase Title: Resolution And Propagation
- Scope: phase-local producer artifact

## Behavior Coverage Map

- Workflow-level default policy resolution:
  - `test_workflow_policy_is_inherited_and_step_policy_overrides`
  - `test_direct_engine_run_propagates_authored_workflow_policy_without_manual_resolver`
- Step-level override resolution:
  - `test_workflow_policy_is_inherited_and_step_policy_overrides`
  - `test_workflow_step_policy_applies_to_inline_operations_in_hooks`
- Reusable policy object reuse:
  - `test_reusable_policy_object_can_be_reused_by_two_steps`
- Inline operation inheritance and explicit `policy=` override:
  - `test_python_step_policy_affects_inline_operations_and_explicit_override_wins`
- Strict-policy parity for step and inline paths:
  - `test_strict_policy_rejects_unsafe_step_and_inline_overrides_with_same_violation`
- Workflow-step hook binding and cleanup:
  - `test_workflow_step_policy_applies_to_inline_operations_in_hooks`
  - `test_workflow_step_hook_does_not_inherit_stale_policy_from_previous_step`
- Topology hash participation:
  - `test_policy_changes_participate_in_topology_hash`
- Replay fingerprint participation with preserved mismatch behavior:
  - `test_operation_replay_fingerprint_changes_when_policy_changes`
  - `tests/contract/test_engine_contracts.py -k 'operation_replay_fingerprint or operation_replay_override or llm_and_classify_step_replay_across_reruns'`

## Preserved Invariants Checked

- Direct `Engine(...)` fallback resolver honors authored policy without changing explicit-resolver paths.
- Workflow-step hooks use the current step/workflow resolution, not a leaked prior-step policy.
- Existing replay mismatch behavior remains `warn`-compatible while fingerprints expand for policy changes.

## Edge Cases And Failure Paths

- Unsafe `danger_full_access` policy is rejected identically for step-level and inline-provider paths.
- Hook-driven inline provider calls on `workflow_step(...)` short-circuit child invocation and still receive the resolved step policy.
- Cross-step cleanup case asserts a following workflow-step hook falls back to workflow policy instead of inheriting a prior prompt-step override.

## Flake Risk / Stabilization

- All tests use `ScriptedLLMProvider`, in-memory stores, fixed prompts, and temp-path workspaces only.
- No network, subprocess, clock-sensitive, or nondeterministic ordering dependencies are introduced.

## Known Gaps

- This phase still does not cover provider-specific emission or CLI/config-file integration; those belong to later policy-emitter phases.
