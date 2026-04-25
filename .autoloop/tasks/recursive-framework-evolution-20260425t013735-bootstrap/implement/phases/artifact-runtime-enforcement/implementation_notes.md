# Implementation Notes

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: implement
- Phase ID: artifact-runtime-enforcement
- Phase Directory Key: artifact-runtime-enforcement
- Phase Title: Artifact Runtime Enforcement
- Scope: phase-local producer artifact

## Files Changed

- `core/engine.py`
- `core/compiler.py`
- `core/validation.py`
- `core/stores/protocols.py`
- `runtime/stores/filesystem.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_compatibility_runtime.py`
- `decisions.txt`

## Symbols Touched

- `Engine._execute_step`
- `Engine._resolve_artifacts`
- `Engine._enforce_artifact_contracts`
- `Engine._required_output_artifacts`
- `Engine._validate_output_artifact`
- `Engine._raise_artifact_validation_error`
- `Engine._save_checkpoint`
- `CompiledStep.route_contracts` for `SystemStep`
- `_validate_control_contracts`
- `CheckpointPayload.failure_context`
- `FilesystemCheckpointStore.save/load`

## Checklist Mapping

- Plan Phase 3 / AC-05: enforced selected-route artifact contracts after handler execution and before route commit for provider-owned and system steps.
- Plan Phase 3 / AC-05: checkpointed artifact validation failures with additive diagnostic context.
- Plan Phase 3 / AC-06: preserved `expected_output_schema` as payload-only validation.

## Assumptions

- Worklist selection snapshots are not yet implemented in this codebase phase; artifact validation checkpoints therefore preserve artifact diagnostics plus the existing state/session snapshot surfaces.

## Preserved Invariants

- `expected_output_schema` still validates only `Outcome.payload`.
- No fallback routing was introduced for missing or invalid artifacts.
- Existing required input artifact behavior (`requires`) remains unchanged.
- `ctx.open_session(..., scope=...)` behavior was not touched in this phase.

## Intended Behavior Changes

- Provider-owned steps now validate required produced artifacts after middleware/handler processing and before route success is committed.
- System steps now apply the same selected-route artifact enforcement and may declare `route_contracts` for that purpose.
- Checkpoints now persist additive `failure_context` for artifact validation failures.

## Known Non-Changes

- No session continuity/default-session refactor.
- No typed routes/effects implementation.
- No worklist/runtime selection implementation.
- No child workflow IO changes.

## Expected Side Effects

- Step-local relative produced artifacts now resolve using compiled owner metadata during runtime handle construction, preventing accidental resolution against the process working directory.

## Validation Performed

- `./.venv/bin/pytest -q tests/contract/test_engine_contracts.py`
- `./.venv/bin/pytest -q tests/unit/test_primitives_and_stores.py tests/unit/test_validation.py`
- `./.venv/bin/pytest -q tests/runtime/test_compatibility_runtime.py -k 'filesystem_session_store or filesystem_checkpoint_store_roundtrips_failure_context'`
- `python3 -m py_compile core/engine.py core/compiler.py core/validation.py core/stores/protocols.py runtime/stores/filesystem.py tests/contract/test_engine_contracts.py tests/runtime/test_compatibility_runtime.py`

## Deduplication / Centralization

- Centralized runtime artifact-contract enforcement in `Engine` helpers instead of duplicating checks across `LLMStep`, `PairStep`, and `SystemStep`.
- Reused the compiled qualified artifact inventory as the single source of truth for runtime output validation.
