# Implementation Notes

- Task ID: task-implement-the-refactor-suggestions-below-to-c2f5dbe1
- Pair: implement
- Phase ID: provider-policy-translators
- Phase Directory Key: provider-policy-translators
- Phase Title: Provider Policy Translators
- Scope: phase-local producer artifact

## Files Changed
- `botlane/runtime/providers/codex_policy.py`
- `botlane/runtime/providers/claude_policy.py`
- `botlane/policy.py`
- `tests/runtime/test_provider_policy_emitters.py`
- `tests/unit/test_policy.py`

## Symbols Touched
- `CodexPolicyEmitter._build_config_payload`
- `ClaudePolicyEmitter._build_settings_payload`
- `Policy`
- `_policy_layer_to_override`
- New private helper dataclasses/maps for Codex, Claude, and public policy lowering

## Checklist Mapping
- Phase 1.1 Codex emitter refactor: complete
- Phase 1.2 Claude emitter refactor: complete
- Phase 1.3 `_policy_layer_to_override` split: complete
- Phase 1 validation expansion: complete
- Out-of-phase items: none

## Assumptions
- Existing payload/message ordering is part of behavioral parity and should not change even when helper extraction is internal only.
- `botlane/*` remains the only source-of-truth edit surface for this phase.

## Preserved Invariants
- Codex emitted config values, unsupported/lossy/unsafe classifications, and `shell_environment_policy` output remain behavior-preserving.
- Claude emitted settings payloads, CLI arg ordering, capability reports, and effective enforcement calculations remain behavior-preserving.
- Public `Policy(...)` incompatibility messages and effective sandbox/network inference remain verbatim-compatible.

## Intended Behavior Changes
- None.

## Known Non-Changes
- No runtime loop, discovery, inventory, or placeholder-validator refactors.
- No `build/lib/*` mirroring or packaging regeneration.

## Deduplication / Centralization
- Introduced module-local translation maps and small helper emitters/state dataclasses instead of cross-module abstractions.
- Centralized public policy effect resolution into explicit sandbox/network inference helpers before payload emission.

## Expected Side Effects
- Lower per-function branching in the three phase-targeted translators.
- Narrower unit-test targets for permission/sandbox/network mapping and exact validation wording.

## Validation Performed
- `.autoloop_test_venv/bin/python -m pytest tests/runtime/test_provider_policy_emitters.py tests/unit/test_policy.py`
- `.autoloop_test_venv/bin/python -m pytest tests/unit/test_simple_policy.py tests/runtime/test_provider_policy_config.py`
