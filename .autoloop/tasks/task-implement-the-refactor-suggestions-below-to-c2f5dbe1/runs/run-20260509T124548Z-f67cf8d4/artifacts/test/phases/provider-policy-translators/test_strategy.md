# Test Strategy

- Task ID: task-implement-the-refactor-suggestions-below-to-c2f5dbe1
- Pair: test
- Phase ID: provider-policy-translators
- Phase Directory Key: provider-policy-translators
- Phase Title: Provider Policy Translators
- Scope: phase-local producer artifact

## Behavior To Coverage Map
- Codex permission-mode translation parity: `tests/runtime/test_provider_policy_emitters.py::test_codex_emitter_maps_supported_permission_modes`
- Codex unsupported/lossy/unsafe classification parity: existing Codex emitter tests plus `test_codex_emitter_reports_disabled_sandbox_as_unsupported` and `test_codex_emitter_reports_unsupported_permission_modes`
- Claude permission-mode and CLI-arg parity: `tests/runtime/test_provider_policy_emitters.py::test_claude_emitter_maps_permission_modes`
- Claude native effective-enforcement parity: `tests/runtime/test_provider_policy_emitters.py::test_claude_emitter_reports_native_effective_enforcement_details`
- Claude failure path for incompatible dangerous-bypass settings: `tests/runtime/test_provider_policy_emitters.py::test_claude_emitter_rejects_unsandboxed_mode_when_disable_bypass_is_enabled`
- Public `Policy(...)` exact incompatibility wording: `tests/unit/test_policy.py::test_policy_same_layer_validation_preserves_exact_messages`
- `simple.Policy(...)` exact incompatibility wording: `tests/unit/test_simple_policy.py::test_simple_policy_validation_preserves_exact_public_messages`

## Preserved Invariants Checked
- Helper extraction did not change emitted approval/default permission modes.
- Claude CLI arg ordering still includes `--dangerously-skip-permissions` only for unsandboxed bypass mode.
- Capability reports still reflect native filesystem/network enforcement versus lossy fallback behavior.
- Public and simple policy surfaces still raise the same user-facing validation messages for high-risk combinations.

## Edge Cases / Failure Paths
- Unsupported Codex permission modes and disabled sandbox handling.
- Claude unsandboxed mode with `disable_dangerous_bypass=True`.
- Read-only plus write roots, limited network without domains, and unsandboxed permission mismatch on both public/simple policy surfaces.

## Flake Risks And Stabilization
- Environment dependency risk: tests were run in a temporary local venv with `pydantic` and `pytest` installed explicitly, avoiding system-package drift.
- Ordering risk: assertions target exact tuples/strings where message or CLI ordering is part of the contract.
- No timing, network, or external-service dependencies are introduced.

## Known Gaps
- No broader runtime-loop or workflow-discovery coverage in this phase; those remain explicitly out of scope.
