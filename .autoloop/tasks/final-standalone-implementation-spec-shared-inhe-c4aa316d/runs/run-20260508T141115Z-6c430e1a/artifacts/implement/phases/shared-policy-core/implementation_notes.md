# Implementation Notes

- Task ID: final-standalone-implementation-spec-shared-inhe-c4aa316d
- Pair: implement
- Phase ID: shared-policy-core
- Phase Directory Key: shared-policy-core
- Phase Title: Shared Policy Core
- Scope: phase-local producer artifact

## Files changed

- `autoloop/policy.py`
- `autoloop/simple.py`
- `tests/unit/test_policy.py`
- `tests/unit/test_simple_policy.py`
- `decisions.txt`

## Symbols touched

- `autoloop.policy.Policy`
- `autoloop.policy.PolicyInput`
- `autoloop.policy.resolve_policy_layer`
- `autoloop.policy._dangerous_manual_permission_override`
- `autoloop.simple._normalize_provider_policy`

## Checklist mapping

- Shared policy module and sparse lowering: complete.
- PolicyInput acceptance in authored workflow/step/operation surfaces: complete for simple/core/runtime surfaces touched in this phase.
- Deterministic authored-layer payload for compiler fingerprinting: complete.
- Public export cleanup for `PolicyOverride`: complete for `autoloop`, `autoloop.simple`, and convenience `autoloop.sdk` policy re-exports.
- Reviewer blocking fixes for dangerous manual sandbox resolution and the leaked internal override symbol: complete.
- SDK naming/runtime-layer work from later plan milestones: deferred to later phases.

## Intended behavior changes

- Public policy authoring now uses sparse inheriting `Policy(...)` instead of eager concrete `simple.Policy(...)`.
- Public root/simple exports no longer expose `PolicyOverride`.
- Public `Policy(sandbox_mode=SandboxMode.DANGER_FULL_ACCESS)` now resolves as dangerous manual access over the default base by forcing `permissions.mode == "ask"` while enabling the required dangerous bypass latch.
- Workflow, step, and inline operation authoring now accept public `Policy` layers directly.

## Preserved invariants

- Core nested provider-policy schema and merge semantics remain unchanged.
- Internal compatibility for concrete `ProviderPolicy` and core `ProviderPolicyOverride` remains intact.
- Runtime strict-policy validation remains the final enforcement boundary.

## Known non-changes

- No SDK `workspace`/`input`/`params` rename work in this phase.
- No runtime config syntax changes.
- No provider emitter changes.

## Validation performed

- `.venv/bin/python -m pytest tests/unit/test_policy.py tests/unit/test_simple_policy.py`
- `.venv/bin/python -m pytest tests/unit/test_policy.py tests/unit/test_simple_policy.py tests/unit/test_simple_surface.py tests/runtime/test_provider_policy_steps.py`
- `.venv/bin/python -m pytest tests/unit/test_provider_policy.py tests/runtime/test_provider_policy_emitters.py tests/runtime/test_provider_policy_config.py tests/unit/test_sdk_facade.py`
- `.venv/bin/python` smoke check covering dangerous manual resolution and confirming `autoloop.simple` no longer exposes `ProviderPolicyOverride`.

## Assumptions and centralization

- `ProviderPolicyRuntimeConfig.default` continues to supply the default concrete base policy, so this phase keeps SDK default/run-layer wiring for later work.
- All public flat-policy coercion and authored-layer serialization are centralized in `autoloop/policy.py`; duplicated simple-surface helpers were removed.
- The dangerous-manual sandbox compatibility adjustment stays centralized in `autoloop/policy.py` rather than being repeated in compiler/runtime callers.
