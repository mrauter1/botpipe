# Implementation Notes

- Task ID: implementation-goal-add-a-first-class-provider-p-5e755cae
- Pair: implement
- Phase ID: policy-codex
- Phase Directory Key: policy-codex
- Phase Title: Codex Emission
- Scope: phase-local producer artifact

## Files Changed
- `autoloop/runtime/providers/codex_policy.py`
- `tests/runtime/test_provider_policy_emitters.py`

## Symbols Touched
- `CodexPolicyEmitter.emit()`
- `ProviderPolicyCapabilityReport.effective_enforcement.read_roots`

## Checklist Mapping
- Plan milestone 4 / phase AC-1:
  Codex now emits run-scoped `config.toml`, `effective_policy.json`, and `capability_report.json` under `<run_dir>/provider_policy/<step-key>/codex/`.
- Plan milestone 4 / phase AC-2:
  Codex capability classification now runs before execution, writes target-scoped reports, emits runtime events, and threads policy metadata into provider results/session metadata.
- Regression control:
  Added focused emitter coverage for the reviewer-reported `read_roots` enforcement mismatch and reran the focused Codex emitter/runtime provider suite.

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
- Codex capability reports no longer echo requested `allow_read` roots as effective enforcement when Codex cannot actually enforce read-root narrowing.

## Known Non-Changes
- Claude emission and transport wiring remain untouched in this phase.
- No new workflow business-logic policy behavior was added outside provider request propagation and transport execution.

## Expected Side Effects
- Policy-bearing Codex turns write runtime-owned artifacts under the run directory.
- Capability validation may now fail a Codex turn before subprocess spawn when unsupported/lossy/unsafe mappings are configured to fail.

## Validation Performed
- `python3 -m py_compile autoloop/runtime/providers/codex_policy.py tests/runtime/test_provider_policy_emitters.py`
- `.venv/bin/python -m pytest tests/runtime/test_provider_policy_emitters.py tests/runtime/test_runtime_providers.py -q`
  Result: `58 passed`

## Deduplication / Centralization
- Centralized Codex artifact emission and capability classification in `codex_policy.py`.
- Centralized the corrected Codex read-root reporting rule in the emitter so downstream transports and traces consume one authoritative capability report.
