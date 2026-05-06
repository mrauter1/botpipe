# Implementation Notes

- Task ID: implementation-goal-add-a-first-class-provider-p-5e755cae
- Pair: implement
- Phase ID: policy-core
- Phase Directory Key: policy-core
- Phase Title: Core Policy Domain
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/provider_policy.py`
- `tests/unit/test_provider_policy.py`
- `.autoloop/tasks/implementation-goal-add-a-first-class-provider-p-5e755cae/runs/run-20260506T190853Z-f707cb4f/artifacts/implement/phases/policy-core/implementation_notes.md`
- `.autoloop/tasks/implementation-goal-add-a-first-class-provider-p-5e755cae/runs/run-20260506T190853Z-f707cb4f/decisions.txt`

## Symbols touched
- `ModelPolicy`
- `PermissionPolicy`
- `WorkspaceFilesystemPolicy`
- `WorkspaceNetworkPolicy`
- `WorkspacePolicy`
- `SandboxPolicy`
- `EnvPolicy`
- `ToolPolicy`
- `InstructionPolicy`
- `TelemetryPolicy`
- `ProviderPolicy`
- `ProviderPolicyOverride`
- `StrictPermissionPolicy`
- `StrictWorkspaceFilesystemPolicy`
- `StrictWorkspaceNetworkPolicy`
- `StrictWorkspacePolicy`
- `StrictSandboxPolicy`
- `StrictEnvPolicy`
- `StrictProviderPolicy`
- `ProviderPolicyValidationConfig`
- `ProviderPolicyViolation`
- `ProviderPolicyError`
- `EffectiveEnforcementReport`
- `ProviderPolicyCapabilityReport`
- `ProviderPolicyEmission`
- `SYSTEM_DEFAULT_PROVIDER_POLICY`
- `merge_provider_policies`
- `validate_against_strict_policy`
- `policy_fingerprint`

## Checklist mapping
- Plan milestone 1 / AC-1: implemented normalized policy model tree, system default, merge rules, fingerprinting, and focused unit coverage.
- Plan milestone 1 / AC-2: implemented strict validation with step-aware error reporting, required deny injection, workspace-root path checks, and non-mutating return behavior.
- Reviewer follow-up: fixed the empty-`limited` workspace-network validation gap and revalidated `with_model_effort()` so convenience helpers cannot create invalid policy objects.
- Deferred intentionally: runtime config parsing, workflow authoring API changes, provider emitters/transports, and runtime resolver wiring remain out of phase.

## Assumptions
- Relative workspace paths are validated against the active workspace root only during strict validation, not normalized into absolute paths inside stored policy models.
- Domain allowlist enforcement uses exact matches plus `*.` wildcard suffix matching; broader URL parsing is deferred.
- Because this phase does not expose any strict-policy escape hatch for empty `limited` network mode, `WorkspaceNetworkPolicy(mode="limited")` now rejects an empty `allow_domains`.

## Preserved invariants
- Policy models are frozen Pydantic models with unknown-key rejection.
- Merge behavior stays explicit: deny lists union in order, allow/ask lists replace, dict-like extras deep merge.
- Strict validation returns a new resolved policy and does not mutate the input layer objects.
- Public convenience helpers now return fully revalidated `ProviderPolicy` instances instead of unchecked `model_copy(...)` results.

## Intended behavior changes
- Introduced first-class provider policy data structures and a system-default sandboxed full-auto baseline in core.
- Introduced path-aware strict policy failures for dangerous sandbox expansion, workspace escapes, forbidden local binding, and disallowed domains.

## Known non-changes
- No runtime config integration.
- No workflow/step authoring surface changes.
- No provider emission or transport execution changes.
- No tracing or runtime event changes.

## Expected side effects
- Later phases can import the core policy module directly for runtime/config/transport integration without duplicating merge or validation logic.
- Equivalent normalized policies now produce stable SHA-256 fingerprints suitable for topology/replay metadata in later phases.

## Validation performed
- `.venv/bin/python -m pytest -q tests/unit/test_provider_policy.py`

## Deduplication / centralization decisions
- Kept all merge semantics, strict checks, fingerprinting, and capability/emission model shapes in `autoloop/core/provider_policy.py`.
- Did not spread path-validation logic into tests or adjacent modules; later runtime/provider phases should reuse this core seam.
