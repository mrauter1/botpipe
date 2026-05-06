# Original intent considered

- Audited the immutable request snapshot at `.autoloop/tasks/implementation-goal-add-a-first-class-provider-p-5e755cae/runs/run-20260506T190853Z-f707cb4f/request.md`, the authoritative raw ledger at `.../raw_phase_log.md`, and the run decision ledger at `.../decisions.txt`.
- Reviewed the run-local plan, implement, and test artifacts under `.../artifacts/plan`, `.../artifacts/implement/phases/*`, and `.../artifacts/test/phases/*`.
- Verified the final codebase seams that own the requested behavior: `autoloop/core/provider_policy.py`, `autoloop/runtime/config.py`, `autoloop/core/steps.py`, `autoloop/simple.py`, `autoloop/core/compiler.py`, `autoloop/runtime/provider_policy_resolver.py`, `autoloop/core/operations.py`, `autoloop/core/providers/models.py`, `autoloop/core/providers/turns.py`, `autoloop/core/providers/rendering.py`, `autoloop/runtime/providers/codex_policy.py`, `autoloop/runtime/providers/claude_policy.py`, `autoloop/runtime/providers/codex.py`, `autoloop/runtime/providers/claude.py`, `autoloop/runtime/provider_backends.py`, and `autoloop/runtime/runner.py`.
- Re-ran the focused regression suite:
  `./.venv/bin/python -m pytest -q tests/unit/test_provider_policy.py tests/runtime/test_provider_policy_config.py tests/runtime/test_provider_policy_steps.py tests/runtime/test_provider_policy_emitters.py tests/runtime/test_runtime_providers.py tests/runtime/test_provider_backends.py tests/runtime/test_runtime_tracing.py`
  Result: `180 passed in 2.38s`.

# Clarifications / superseding decisions

- No later raw-log clarification changed the requested behavior. The audit therefore treated the immutable request snapshot as controlling intent.
- The decisions ledger narrowed a few implementation seams without removing requested behavior:
  - Runtime policy ownership stays centralized in `ProviderPolicyResolver`; `provider_backends` remains backend-selection-only.
  - The authoritative emitted artifact contract is target-scoped under `<run_dir>/provider_policy/<step-key>/<target>/...`.
  - `merge_provider_policies()` intentionally starts from the normalized `ProviderPolicy()` baseline; the runtime resolver adds `SYSTEM_DEFAULT_PROVIDER_POLICY` explicitly as the first merge layer.
  - Codex capability reports must not pretend narrowed `allow_read` roots are enforced when Codex has no read-root enforcement surface.
  - Claude policy-backed turns isolate settings in a run-owned location and re-add workspace access via `--add-dir`, rather than mutating or merging user/project Claude settings.

# Implemented behavior

- The core policy domain is present in `autoloop/core/provider_policy.py`: normalized immutable policy models, strict-policy models, `SYSTEM_DEFAULT_PROVIDER_POLICY`, merge helpers, strict validation, capability/emission report models, and stable policy fingerprinting. `tests/unit/test_provider_policy.py` covers defaults, merge semantics, strict validation, symlink escape handling, and fingerprint stability.
- Runtime config integration is present in `autoloop/runtime/config.py` and CLI plumbing. `provider_policy.default`, `provider_policy.strict`, `provider_policy.validation`, `--policy-file`, and validation-mode CLI overrides are parsed with strict unknown-key rejection preserved. Legacy provider model/effort fields and `runtime.full_auto` are mirrored into `provider_policy.default` only when newer policy fields do not already own those knobs. `tests/runtime/test_provider_policy_config.py` covers these paths, including the no-PyYAML narrow loader support for the requested list/null examples.
- Workflow and step authoring support landed in `autoloop/core/steps.py`, `autoloop/simple.py`, and `autoloop/core/compiler.py`: workflow-level `policy`, reusable `ProviderPolicy` objects, per-step overrides, compiled workflow/step policy retention, and topology-hash participation. `tests/runtime/test_provider_policy_steps.py` covers workflow inheritance, step overrides, reusable policy reuse, strict rejection, python-step inline-provider scope, explicit operation overrides, direct-engine fallback behavior, and replay/topology participation.
- Per-turn resolution and propagation are implemented in `autoloop/runtime/provider_policy_resolver.py`, `autoloop/core/operations.py`, `autoloop/core/providers/models.py`, `autoloop/core/providers/turns.py`, `autoloop/core/providers/rendering.py`, `autoloop/core/engine_collaborators.py`, `autoloop/core/engine.py`, and `autoloop/runtime/runner.py`. Resolved policy now flows through provider requests, rendered turns, inline `llm()` / `classify()` calls, operation replay fingerprints, and runtime policy events.
- Provider-specific emission is implemented in `autoloop/runtime/providers/codex_policy.py` and `autoloop/runtime/providers/claude_policy.py`, with transport integration in `autoloop/runtime/providers/codex.py` and `autoloop/runtime/providers/claude.py`. Each policy-backed turn emits run-scoped config/settings, redacted `effective_policy.json`, `capability_report.json`, provider metadata, and runtime events without mutating user-level provider config files. `tests/runtime/test_provider_policy_emitters.py`, `tests/runtime/test_runtime_providers.py`, and `tests/runtime/test_provider_backends.py` cover emitter mappings, capability failure/warn behavior, transport wiring, policy metadata, and backend-compatibility invariants.

# Unresolved gaps

- No material unresolved gaps were found.
- I did not find requested behavior that was absent, materially different, or insufficiently tested once the final codebase, run decisions, and focused regression suite were reconciled.

# Differences justified by later clarification or analysis

- `autoloop/runtime/tracing.py` did not need a policy-specific structural rewrite. The existing generic runtime-event writer already persisted the new policy events once the emitters and step/operation binding sites started calling it. This preserves intent without unnecessary trace-format churn.
- `autoloop/runtime/provider_backends.py` remained a thin built-in backend selector. That matches both the original “do not bury normalized policy logic inside codex.py or claude.py” intent and the later decision to keep runtime policy ownership outside backend dispatch.
- The emitted artifact layout is target-scoped under `<run_dir>/provider_policy/<step-key>/<target>/...` rather than using one shared top-level effective-policy file per step. This matches the later authoritative decision and avoids ambiguity when the same resolved policy is emitted to different providers with different capability reports.
- Codex capability reports intentionally leave `effective_enforcement.read_roots` empty for narrowed `allow_read` policies, because the Codex surface does not enforce read-root narrowing. This is an analysis-backed correction that avoids overstating enforcement.
- Claude policy-backed execution uses run-owned isolated settings state plus `--add-dir` and `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1`. That is an implementation detail chosen to satisfy the request’s “do not mutate user-level provider config files” requirement while preserving workspace access and project instruction loading.

# Recommended next run

- No follow-up implementation run is required for this request.
- Optional future work remains the explicitly deferred non-goals from the original request: MCP, hooks, subagents, plugins, managed-enterprise emitters, and broader provider-backend expansion.
