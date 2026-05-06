# Test Strategy

- Task ID: implementation-goal-add-a-first-class-provider-p-5e755cae
- Pair: test
- Phase ID: policy-core
- Phase Directory Key: policy-core
- Phase Title: Core Policy Domain
- Scope: phase-local producer artifact

## Behavior-to-test coverage

- System default baseline:
  `test_system_default_policy_matches_requested_baseline`
  Verifies sandboxed full-auto defaults, workspace-write sandbox mode, network full, and env deny defaults.

- Merge semantics:
  `test_merge_provider_policies_applies_scalar_union_and_replace_rules`
  Verifies scalar override, deny-list union, allow-write replacement, env set deep merge, and provider-extra deep merge.

- Empty limited-network rejection:
  `test_workspace_network_policy_rejects_empty_limited_mode`
  `test_provider_policy_rejects_empty_limited_network_mode`
  Verifies both direct model construction and top-level `ProviderPolicy` construction reject `mode="limited"` without `allow_domains`.

- Convenience helper validation:
  `test_with_model_effort_revalidates_literal_values`
  `test_with_model_effort_returns_updated_policy_without_mutating_original`
  Verifies invalid effort literals fail and valid helper use updates a new policy without mutating the original instance.

- Strict failure paths:
  `test_strict_policy_rejects_danger_full_access`
  `test_strict_policy_rejects_disabled_sandbox_when_required`
  `test_strict_policy_rejects_write_path_outside_allowed_roots_with_step_context`
  `test_strict_policy_rejects_local_binding_when_forbidden`
  `test_strict_policy_rejects_domains_outside_allowed_domains`
  `test_strict_policy_detects_symlink_escape_according_to_policy`
  Verifies path-aware and policy-aware rejection paths required by the phase.

- Strict non-mutating injection:
  `test_strict_policy_injects_required_denies_without_mutating_input`
  Verifies required deny injection and preserved immutability of earlier layers.

- Fingerprint stability:
  `test_policy_fingerprint_is_stable_for_equivalent_policies`
  Verifies equivalent normalized policies hash identically.

## Preserved invariants checked

- Frozen policy objects remain copy-on-write from the caller perspective.
- System default policy stays separate from generic `ProviderPolicy()` defaults.
- Strict validation returns a resolved policy instead of mutating input objects in place.

## Edge cases and failure paths

- Empty limited-network allowlist.
- Invalid model-effort literal through the public helper path.
- Symlink escape through a relative workspace path.
- Unsafe absolute write root outside strict workspace roots.

## Stabilization / flake controls

- Uses pure unit tests only; no network, subprocesses, or timing-sensitive assertions.
- Uses `tmp_path` for filesystem isolation and local symlink setup.

## Known gaps

- Runtime config mapping, workflow authoring propagation, provider emission, and transport integration remain intentionally out of phase.
- This phase does not exercise the fallback YAML loader or runtime resolver because those belong to later phases.
