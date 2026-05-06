# Provider Policy Plan

## Objective
Add a first-class provider policy layer that resolves once per provider turn or operation, validates against an optional strict envelope, emits run-scoped Codex or Claude policy artifacts, and preserves all existing provider-selection and legacy config behaviors unless the request explicitly changes them.

## Verified Constraints
- Keep built-in backend dispatch limited to `codex` and `claude`; `module:function` provider names remain invalid.
- Keep normalized policy logic outside `autoloop/runtime/providers/codex.py` and `autoloop/runtime/providers/claude.py`; transports should consume a resolved policy plus emission artifacts.
- Preserve strict runtime-config unknown-key rejection and existing generic/provider-specific model and effort merge semantics.
- Preserve fake CLI/subprocess test patterns; no real Codex or Claude binaries in tests.
- Never write user-level provider config files; all generated policy files live under `<run_dir>/provider_policy/...`.
- Extend the no-PyYAML narrow loader because the requested `provider_policy` examples require lists and null values.

## Architecture Shape
- Core domain: add `autoloop/core/provider_policy.py` for Pydantic policy models, merge helpers, strict-policy models, strict validation, capability-report models, emission models, and stable fingerprinting.
- Runtime config: extend `autoloop/runtime/config.py` with `ProviderPolicyRuntimeConfig` on `ResolvedRuntimeConfig`; map legacy provider model and effort fields plus `runtime.full_auto` into `provider_policy.default` during resolution instead of removing legacy fields.
- Authoring and compilation: add optional workflow-level `policy` plus per-step `policy`; store authored policy metadata on `CompiledWorkflow` and `CompiledStep`, and include policy fingerprints in topology hashing.
- Runtime resolution: add `ProviderPolicyResolver` in `autoloop/runtime/provider_policy_resolver.py` to merge system defaults, runtime/config defaults, workflow policy, step or operation overrides, then strict validation.
- Ownership seam: keep `autoloop/runtime/runner.py` responsible for passing `ResolvedRuntimeConfig.provider_policy` plus workspace and run paths into one resolver handoff; keep `autoloop/runtime/provider_backends.py` as backend selection only; keep `engine_collaborators` and operation binding as the runtime consumers of the resolver output.
- Provider boundary: add resolved policy to provider request dataclasses, `ProviderTurnContext`, and `RenderedProviderTurn`; policy summaries must redact env values.
- Emission and execution: implement provider-specific emitters in `codex_policy.py` and `claude_policy.py`, then integrate transport execution so each turn receives emitted CLI args, config file paths, env overrides, and a capability report.
- Observability: trace policy resolution, emission, violations, and capability-report decisions without logging secret env values or headers.

## Milestones

### 1. Core Policy Model And Validation
- Add the policy model tree, system default constant, merge rules, strict-policy model tree, validation config, capability report types, emission types, and fingerprinting.
- Keep models immutable or copy-on-write and canonicalize list-like fields by de-duplicating while preserving order.
- Implement strict path validation against workspace root using canonical path checks, nearest existing parent fallback, and symlink-escape enforcement.
- Treat unsupported or lossy provider features as capability-report outcomes, not hidden emitter behavior.
- Validation:
  - `tests/unit/test_provider_policy.py` covers system defaults, merge semantics, strict rejection and injection, network rules, symlink escape handling, and stable fingerprints.

### 2. Runtime Config And Authoring Surfaces
- Extend runtime config parsing with top-level `provider_policy.default`, `provider_policy.strict`, and `provider_policy.validation`.
- Add CLI flags for `--policy-file` and the three policy-validation overrides.
- Load an optional policy file as another runtime-config merge layer rather than a separate mutation path.
- Map existing `provider.codex.model`, `provider.codex.model_effort`, `provider.claude.model`, `provider.claude.effort`, and `runtime.full_auto` into the resolved default provider policy while keeping the legacy fields intact.
- Add optional `policy` to workflow classes, core step classes, and simple authoring helpers including `python_step`, with documentation that Python-step policy only governs nested provider operations.
- Validation:
  - `tests/runtime/test_provider_policy_config.py` covers defaults, merge order, policy-file overrides, unknown-key rejection, enum-path errors, legacy model and effort mapping, and `full_auto` mapping.
  - Existing provider config tests continue to pass unchanged.

### 3. Compilation, Resolution, And Request Propagation
- Store authored workflow and step policy metadata on compiled objects and include their serialized fingerprints in topology hashing.
- Add `policy` to provider request models, `ProviderTurnContext`, `RenderedProviderTurn`, and `OperationRuntime`.
- Extend the public inline operation surface with `llm_call(..., policy: ProviderPolicy | ProviderPolicyOverride | None = None)` and `classify_call(..., policy: ProviderPolicy | ProviderPolicyOverride | None = None)`, and make `python_step(policy=...)` govern only nested provider operations inside the step.
- Implement `ProviderPolicyResolver.resolve_for_step()` and `.resolve_for_operation()` as the single merge-and-validate seam for runtime use.
- Bind operation runtime with the current resolved step policy so `llm()` and `classify()` inherit by default, while explicit operation policies still pass through strict validation.
- Include policy fingerprints in provider metadata, operation replay fingerprints, and runtime events.
- Validation:
  - `tests/runtime/test_provider_policy_steps.py` covers workflow inheritance, step overrides, reusable policy objects, strict rejection, Python-step operation inheritance, and explicit operation override behavior.
  - Operation replay coverage asserts that the resolved policy fingerprint changes when the new public `policy=` override changes and that strict-policy rejection is identical for step-level and inline-provider paths.
  - Existing topology and replay behavior remains compatible except for the intentional fingerprint expansion.

### 4. Codex Emission And Transport Integration
- Add `CodexPolicyEmitter` to generate the authoritative target-scoped files under `<run_dir>/provider_policy/<step-key>/codex/`: `config.toml`, `effective_policy.json`, and `capability_report.json`.
- Define `<step-key>` as the stable safe-step identifier composed from step name plus scope, item id, and visit when present so emitted files and metadata remain predictable across traces and resume paths.
- Keep Codex capability handling explicit: map supported approval and sandbox knobs; record unsupported `deny_read`, `deny_write`, domain filtering, and managed bypass-disable behavior as unsupported or lossy.
- Integrate emitted CLI args and env into both async transport and sync operation executor without moving normalized policy logic into the transport module.
- Attach `provider_metadata["policy"] = {"effective_policy_file": "...", "capability_report_file": "...", "policy_fingerprint": "..."}` while preserving session resume and cross-provider session guards.
- Validation:
  - `tests/runtime/test_provider_policy_emitters.py` adds Codex emission and capability-report cases.
  - Existing Codex provider transport tests are extended to assert config args, env propagation, target-scoped metadata paths, and stable step-key usage using fake subprocess helpers.

### 5. Claude Emission, Runtime Observability, And Final Regression Sweep
- Add `ClaudeCapabilities` and `ClaudePolicyEmitter` to generate the authoritative target-scoped files under `<run_dir>/provider_policy/<step-key>/claude/`: `settings.json`, `effective_policy.json`, and `capability_report.json`.
- Emit native filesystem and network sandbox settings when capabilities allow; otherwise emit permission-rule approximations and mark enforcement as lossy.
- Add runtime trace events for `provider_policy_resolved`, `provider_policy_emitted`, `provider_policy_violation`, and `provider_policy_capability_report`, each carrying step name, step execution id, provider target, policy fingerprint, capability report path, and decision while excluding secret-bearing values.
- Finish provider-transport coverage, runtime integration coverage, and config-example documentation updates.
- Validation:
  - `tests/runtime/test_provider_policy_emitters.py` adds Claude capability-profile and unsafe-expansion cases.
  - Provider transport tests cover safe settings injection, strict failure when enforcement is unavailable, emitted metadata payloads, and unchanged cross-provider resume behavior.
  - Docs or examples show the intended config shape and reusable workflow policy objects.

## Interfaces To Implement
- `autoloop/core/provider_policy.py`
  - `ProviderPolicy`, `ProviderPolicyOverride`, `ResolvedProviderPolicy`, `StrictProviderPolicy`, supporting nested policy models, `ProviderPolicyError`, `ProviderPolicyViolation`, `ProviderPolicyCapabilityReport`, `ProviderPolicyEmission`, `merge_provider_policies()`, `validate_against_strict_policy()`, `policy_fingerprint()`, and `SYSTEM_DEFAULT_PROVIDER_POLICY`.
- `autoloop/runtime/config.py`
  - `ProviderPolicyRuntimeConfig` and `ProviderPolicyValidationConfig` added to the resolved runtime config path, plus CLI and policy-file merge support.
- `autoloop/core/steps.py` and `autoloop/simple.py`
  - Optional `policy` arguments for step declarations and workflow-level policy capture.
- `autoloop/core/operations.py`
  - `llm_call(..., policy: ProviderPolicy | ProviderPolicyOverride | None = None)`, `classify_call(..., policy: ProviderPolicy | ProviderPolicyOverride | None = None)`, and `OperationRuntime.policy` so inline operations can inherit or explicitly override the current step policy without bypassing strict validation.
- `autoloop/core/compiler.py`
  - `CompiledWorkflow.provider_policy` and `CompiledStep.provider_policy`, with topology hash serialization of stable policy fingerprints.
- `autoloop/core/providers/models.py`, `autoloop/core/providers/rendering.py`, `autoloop/core/providers/turns.py`
  - Resolved policy propagation into request, context, and rendered turn objects.
- `autoloop/runtime/provider_policy_resolver.py`
  - `ProviderPolicyResolver(config, workflow_policy, workspace_root)` with `resolve_for_step()` and `resolve_for_operation()`.
- `autoloop/runtime/providers/codex_policy.py` and `autoloop/runtime/providers/claude_policy.py`
  - Provider-specific emitters returning `ProviderPolicyEmission(target, config_files, cli_args, env, capability_report)` and writing authoritative target-scoped `effective_policy.json` and `capability_report.json` files.
- `autoloop/runtime/runner.py`, `autoloop/runtime/provider_backends.py`, and `autoloop/core/engine_collaborators.py`
  - Runner owns the resolved runtime policy handoff, provider backends remain selector-only, and engine collaborators or operation binding consume the resolver output when constructing provider requests.

## Run-Scoped Artifact Contract
- Use `<run_dir>/provider_policy/<step-key>/` as the parent directory for all emitted policy artifacts for a resolved turn.
- `<step-key>` must be a stable safe identifier derived from step name and include scope name, item id, and visit when those values exist.
- Codex files are authoritative under `<run_dir>/provider_policy/<step-key>/codex/` and must include `config.toml`, `effective_policy.json`, and `capability_report.json`.
- Claude files are authoritative under `<run_dir>/provider_policy/<step-key>/claude/` and must include `settings.json`, `effective_policy.json`, and `capability_report.json`.
- `ProviderPolicyEmission` must carry the target name, emitted config file mapping, CLI args, env overrides, and the capability report object for that exact target emission.
- Provider metadata must expose `effective_policy_file`, `capability_report_file`, and `policy_fingerprint` under `provider_metadata["policy"]`.
- Runtime trace payloads for policy events must include step name, step execution id, provider target, policy fingerprint, capability report path, and decision, but never env values, headers, tokens, or secrets.

## Compatibility And Regression Controls
- Existing configs without `provider_policy` continue to resolve to the requested system default policy.
- Existing `provider.*` model and effort fields remain first-class inputs; policy resolution mirrors them instead of replacing them in this patch.
- Existing Claude `permission_strategy` remains supported for backward compatibility; plan the new policy layer so it can coexist with the old field during the patch.
- Existing `runtime.full_auto` keeps working and maps to `provider_policy.default.permissions.mode="full_auto_sandboxed"` unless a more specific policy mode already overrides it later in resolution.
- Operation replay mismatch handling stays unchanged except that the fingerprint now includes the policy fingerprint.
- The new public `policy=` overrides on `llm()` and `classify()` are additive only; callers that omit them keep existing behavior and inherit the current step policy when a runtime is bound.
- Generated policy files are runtime-owned artifacts only; do not treat them as user-authored config or write them into home-directory provider settings.

## Validation Strategy
- Run the new focused policy test files plus existing provider backend and runtime provider suites.
- Re-run topology-hash, operation replay, and runtime tracing tests touched by request-shape changes.
- Verify both async transport execution and sync operation-executor paths for Codex and Claude.
- Verify secret redaction by asserting traces and capability reports include policy fingerprints and paths but not env values or secret-looking headers.

## Risk Register
- Risk: Config parsing regresses in environments without PyYAML because requested policy examples use lists and nulls.
  - Mitigation: extend the narrow YAML parser in the same patch and add no-PyYAML coverage for nested `provider_policy`.
- Risk: Strict policy checks drift between step execution and inline operations.
  - Mitigation: route both through `ProviderPolicyResolver`; do not duplicate merge or validation logic in transports or operation helpers.
- Risk: Policy metadata changes destabilize resume or replay behavior.
  - Mitigation: keep fingerprints stable, add explicit tests for replay mismatch semantics and cross-provider session guards, and preserve provider name checks.
- Risk: Emitters overstate provider enforcement for unsupported features.
  - Mitigation: require capability reports to classify unsupported, lossy, and unsafe mappings before provider execution and gate failures through validation modes.
- Risk: Secret-bearing env data leaks into prompts or traces.
  - Mitigation: redact env values in summaries and events, serialize only policy structure and fingerprints, and add tests that inspect trace payloads.

## Rollout And Rollback
- Roll out in ordered phases so core policy semantics and config compatibility land before provider execution changes.
- If a later phase fails, rollback at the provider-emitter seam by disabling the transport integration while keeping the pure policy-model and config work intact.
- Do not ship partial transport behavior that writes provider config files without also producing capability reports and validation decisions.
