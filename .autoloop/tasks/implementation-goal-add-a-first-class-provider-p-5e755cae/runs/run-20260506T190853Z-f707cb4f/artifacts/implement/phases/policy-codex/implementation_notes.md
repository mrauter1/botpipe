# Implementation Notes

- Task ID: implementation-goal-add-a-first-class-provider-p-5e755cae
- Pair: implement
- Phase ID: policy-codex
- Phase Directory Key: policy-codex
- Phase Title: Codex Emission
- Scope: phase-local producer artifact

## Files Changed
- `autoloop/runtime/providers/codex_policy.py`
- `autoloop/runtime/providers/codex.py`
- `autoloop/runtime/providers/_common.py`
- `autoloop/core/providers/rendering.py`
- `autoloop/core/providers/turns.py`
- `tests/runtime/test_provider_policy_emitters.py`
- `tests/runtime/test_runtime_providers.py`
- `tests/runtime/test_provider_backends.py`
- `autoloop/runtime/config.py`

## Symbols Touched
- `RenderedProviderTurn`
- `render_provider_turn_with_policy()`
- `run_text_subprocess()`
- `merge_subprocess_env()`
- `build_policy_step_key()`
- `CodexPolicyEmitter.emit()`
- `CodexTransport.run_turn()`
- `build_codex_transport()`
- `build_codex_operation_executor()`
- `resolve_codex_cli_commands()`
- `_merge_provider_policy_config()`

## Checklist Mapping
- Plan milestone 4 / phase AC-1:
  Codex now emits run-scoped `config.toml`, `effective_policy.json`, and `capability_report.json` under `<run_dir>/provider_policy/<step-key>/codex/`.
- Plan milestone 4 / phase AC-2:
  Codex capability classification now runs before execution, writes target-scoped reports, emits runtime events, and threads policy metadata into provider results/session metadata.
- Regression control:
  Added focused emitter tests, transport tests, and backend command-resolution coverage.
- Intentional adjacent fix:
  `autoloop/runtime/config.py` now aliases legacy Claude `model_effort=max` to policy `xhigh` only for the provider-policy mirror path so existing provider-backend compatibility tests still pass.

## Assumptions
- Codex CLI honors `$CODEX_HOME/config.toml`; the run-scoped policy directory is therefore the safest non-mutating config seam for this phase.
- Runtime/provider turns already carry resolved policy whenever the runner/engine policy resolver is in play; direct transport tests without policy remain supported.

## Preserved Invariants
- Backend dispatch still stays limited to built-in `codex` and `claude`.
- No user-level provider config file is written.
- Session resume and cross-provider resume guards remain unchanged.
- Legacy provider model/model-effort fields remain supported.

## Intended Behavior Changes
- Codex approval/sandbox mode is now driven by emitted per-turn policy artifacts instead of a hard-coded full-auto CLI flag.
- Provider metadata now includes policy artifact paths and the resolved policy fingerprint when a turn carries policy.
- Runtime emits `provider_policy_emitted` and `provider_policy_capability_report` for Codex turns with policy.

## Known Non-Changes
- Claude emission and transport wiring remain untouched in this phase.
- No new workflow business-logic policy behavior was added outside provider request propagation and transport execution.

## Expected Side Effects
- Policy-bearing Codex turns write runtime-owned artifacts under the run directory.
- Capability validation may now fail a Codex turn before subprocess spawn when unsupported/lossy/unsafe mappings are configured to fail.

## Validation Performed
- `python3 -m py_compile autoloop/runtime/providers/codex.py autoloop/runtime/providers/codex_policy.py autoloop/core/providers/rendering.py autoloop/core/providers/turns.py autoloop/runtime/providers/_common.py`
- `.autoloop-test-venv/bin/python -m pytest tests/runtime/test_provider_policy_emitters.py tests/runtime/test_runtime_providers.py tests/runtime/test_provider_backends.py -q`
  Result: `97 passed`

## Deduplication / Centralization
- Centralized Codex artifact emission and capability classification in `codex_policy.py`.
- Centralized stable step-key and subprocess env helpers in `_common.py`.
