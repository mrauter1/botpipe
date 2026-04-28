# Implementation Notes

- Task ID: standalone-implementation-plan-final-autoloop-v3-f607e24e
- Pair: implement
- Phase ID: retry-aware-event-validation
- Phase Directory Key: retry-aware-event-validation
- Phase Title: Retry-Aware Event Validation
- Scope: phase-local producer artifact

## Files changed

- `core/engine.py`
- `tests/contract/test_engine_contracts.py`
- `decisions.txt`

## Symbols touched

- `Engine._validate_event`
- `Engine._finalize_step_result`
- `Engine._run_after_hook`
- `Engine._normalize_after_hook_result`
- `Engine._apply_outcome`
- `Engine._execute_step`
- `Engine._execute_workflow_step`

## Checklist mapping

- Step 1.1-1.5: implemented shared event validation, provider/deterministic attribution, and finalization wiring in `core/engine.py`.
- Step 1.6: added engine contract coverage for provider retries, retry exhaustion, deterministic system failures, hook behavior, middleware illegal routes, and malformed child-workflow pause mapping.
- Phase-only note: later cleanup phases still own generated workflow-step residue, `BoardMutation`, naming cleanup, payload cleanup, and docs/docstrings outside this event-validation scope.

## Intended behavior changes

- Invalid `Event` payloads now fail centrally through `_validate_event(...)` instead of relying on later route lookup or checkpointing.
- Provider-step invalid Events from middleware, provider-default events, and route-string hook retags now surface as `ProviderExecutionError` with retry metadata (`illegal_route` or `invalid_payload`) and reuse the existing retry loop.
- Explicit hook-returned `Event` values now cross a deterministic boundary: invalid final Events and final artifact failures hard-fail with `WorkflowExecutionError`.
- Workflow-step child pause/fail mapping is now validated before finalization, so malformed child pause questions cannot persist.

## Preserved invariants

- `_validate_outcome(...)` remains the provider `Outcome` validator and still owns malformed provider-output metadata.
- `_next_retry_feedback(...)` routing was left unchanged; the phase relies on its existing support for `illegal_route`, `invalid_payload`, `missing_required_output_artifact`, `invalid_output_artifact`, `malformed_provider_output`, and `provider_transport_failure`.
- Invalid PAUSE/FAIL events are rejected before checkpoint persistence because candidate and final events are validated inside `_finalize_step_result(...)`.

## Assumptions and non-changes

- Deterministic illegal-route failures now surface as `WorkflowExecutionError` messages from `_validate_event(...)` rather than falling through to `RoutingError`; this stays within the requested hard-fail contract.
- No new retry loop, checkpoint schema, or provider contract shape was introduced.
- This phase did not modify generated workflow-step lowering, `BoardMutation`, naming cleanup, payload cleanup, or docs outside the touched test expectations.

## Validation performed

- `python3 -m py_compile core/engine.py tests/contract/test_engine_contracts.py`
- Attempted targeted `pytest` selection, but `pytest` is not installed in this environment.
- Attempted direct runtime smoke script, but the interpreter environment is missing `pydantic`, so import-time execution is blocked.

## Deduplication / centralization decisions

- Event payload and legal-route checks were centralized in `Engine._validate_event(...)`.
- Final-event attribution is derived once at the after-hook boundary via the explicit-event override flag returned from `_normalize_after_hook_result(...)`.
