# Test Strategy

- Task ID: implementation-goal-add-a-first-class-provider-p-5e755cae
- Pair: test
- Phase ID: policy-claude-regression
- Phase Directory Key: policy-claude-regression
- Phase Title: Claude Emission And Regression Sweep
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- Claude run-scoped emission and isolation:
  - `tests/runtime/test_provider_policy_emitters.py`
    - `test_claude_emitter_maps_allow_write_and_disable_bypass`
    - `test_claude_emitter_maps_deny_read_and_deny_write_to_sandbox_and_permission_rules`
    - `test_claude_emitter_maps_network_domains`
  - `tests/runtime/test_runtime_providers.py`
    - `test_claude_transport_emits_run_scoped_policy_artifacts_and_metadata`
    - `test_claude_operation_executor_uses_policy_settings_and_metadata`
- Capability gating and degraded enforcement:
  - `tests/runtime/test_runtime_providers.py`
    - `test_verify_claude_code_capabilities_rejects_missing_settings_flag`
    - `test_verify_claude_code_capabilities_rejects_missing_add_dir_flag`
  - `tests/runtime/test_provider_policy_emitters.py`
    - `test_claude_emitter_marks_filesystem_capability_lossy_when_native_support_is_missing`
    - `test_claude_emitter_marks_default_workspace_write_lossy_when_native_support_is_missing`
    - `test_claude_emitter_raises_when_lossy_mapping_is_fail`
  - `tests/runtime/test_runtime_providers.py`
    - `test_claude_transport_marks_capability_loss_when_native_filesystem_support_is_missing`
- Legacy Claude compatibility:
  - `tests/runtime/test_provider_policy_config.py`
    - `test_resolve_runtime_config_maps_legacy_claude_bypass_into_provider_policy`
    - `test_explicit_policy_fields_beat_legacy_claude_bypass_mapping`
  - `tests/runtime/test_runtime_providers.py`
    - `test_claude_transport_preserves_legacy_bypass_for_policy_backed_turns`
    - `test_claude_transport_does_not_reapply_legacy_bypass_when_explicit_policy_is_safe`
- Preserved invariants and adjacent regressions:
  - `tests/runtime/test_provider_backends.py`
  - `tests/runtime/test_provider_policy_steps.py`
  - existing `tests/runtime/test_runtime_providers.py` cross-provider resume and metadata assertions

## Edge Cases And Failure Paths

- Missing CLI surfaces fail deterministically before provider execution.
- Default workspace-write fallback still reports lossy enforcement when native Claude filesystem settings are unavailable.
- Explicit authored/runtime policy fields prevent legacy `permission_strategy=bypass` from silently widening policy.

## Stabilization Notes

- All subprocess and CLI-help interactions remain fully stubbed; no real Claude or Codex binary is invoked.
- Workspace and run directories are created under `tmp_path` so path-sensitive assertions stay deterministic.

## Known Gaps

- No live-Claude integration test exists for managed enterprise settings precedence; this phase intentionally keeps coverage at the fake CLI surface.
- Additional-directory `CLAUDE.md` loading is validated indirectly through emitted env/cwd/CLI args rather than a real Claude process.
- The adjacent `tests/runtime/test_provider_policy_steps.py` suite currently fails in this environment because the optional `jsonschema` dependency is unavailable during route-contract compilation; this turn did not broaden into unrelated dependency or fixture repair work.
