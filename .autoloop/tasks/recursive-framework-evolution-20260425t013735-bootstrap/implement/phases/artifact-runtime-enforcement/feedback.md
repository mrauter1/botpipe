# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: implement
- Phase ID: artifact-runtime-enforcement
- Phase Directory Key: artifact-runtime-enforcement
- Phase Title: Artifact Runtime Enforcement
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` [core/engine.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/engine.py): `_execute_step()` now enforces output-artifact contracts before it resolves the selected route with `self.compiled.route(...)`. That masks routing errors whenever middleware or a system handler emits an invalid tag and the step also has a missing/invalid required output. Repro: an `on_outcome()` hook returning `Event("bogus")` on a step with `Artifact(..., required=True)` now raises `ProviderExecutionError` for artifact validation instead of the expected routing failure, so the checkpoint and surfaced error point at the wrong problem. Minimal fix: centralize selected-route resolution ahead of `_enforce_artifact_contracts(...)` for all step kinds, then run artifact validation against the already-resolved route tag/destination so illegal routes still fail first as required by the phase plan.
- IMP-001 `resolved` reviewer recheck: `core/engine.py` now resolves the selected route before output-artifact enforcement for provider-owned and system steps, and the focused regression slice passes including `test_invalid_middleware_route_still_fails_before_artifact_validation`. No remaining phase-local findings.
