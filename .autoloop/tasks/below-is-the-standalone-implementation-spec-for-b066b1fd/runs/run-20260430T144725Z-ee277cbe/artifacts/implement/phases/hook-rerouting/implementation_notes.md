# Implementation Notes

- Task ID: below-is-the-standalone-implementation-spec-for-b066b1fd
- Pair: implement
- Phase ID: hook-rerouting
- Phase Directory Key: hook-rerouting
- Phase Title: Enable Hook Rerouting
- Scope: phase-local producer artifact

## Files changed

- `core/engine.py`
- `core/context.py`
- `core/extensions.py`
- `core/validation.py`
- `runtime/tracing.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_runtime_tracing.py`
- `tests/unit/test_validation.py`

## Symbols touched

- `Engine._finalize_step_result`
- `Engine._run_after_hook`
- `Engine._run_route_hook`
- `Engine._normalize_hook_result`
- `Engine.max_hook_redirects`
- `Context.event`
- `StepFinish`
- `HookRouteRedirect`
- `_validate_step_hooks`
- `_validate_static_after_hook_redirect_policy`
- `RuntimeTraceWriter._write_step_finished`

## Checklist mapping

- Milestone 2 / allow `str` and `Event` hook returns: implemented in `core/engine.py` for `after`, `after_verifier`, `on_route`, and `on_taken`.
- Milestone 2 / chained route-finalization with cap: implemented with restart-on-redirect loop and `max_hook_redirects = 16`.
- Milestone 2 / hook redirect observability: added `hook_route_redirected` sink events plus `candidate_route`, `final_route`, and redirect-chain trace payloads.
- Milestone 2 / update redirect rejection tests: replaced old rejection assertions with reroute, invalid-route, chain, final-route-validation, and cycle coverage.
- Reviewer follow-up / producer-phase validation parity: static `after_do` hook overrides are now rejected at validation time so compiler behavior matches the runtime rule that rerouting starts only after a candidate event exists.

## Assumptions

- Producer-phase `after_producer` hooks remain state-only because no candidate route exists yet.
- Same-tag Event overrides are treated as hook-owned final events for validation attribution, but not as route redirects.

## Preserved invariants

- Redirect targets must already be declared route tags on the current step.
- Provider-originated illegal routes still use provider-attributable errors unless a hook overrides the candidate event.
- Route-finalization continues to re-resolve artifacts between hooks.

## Intended behavior changes

- `after` / `after_verifier` hooks may now return a route tag, `Event`, or structured `AfterStepResult` override.
- `on_route` and route-level `on_taken` hooks may reroute and chaining continues through the redirected route’s hooks.
- Route-hook failures and redirect-limit failures roll workflow state, step state stores, item state stores, step-item state stores, and sessions back to the pre-route-finalization snapshot.

## Known non-changes

- No StateVar, built-in runtime state, item-state authoring, effective-required-write rendering, or history-reader work was added in this phase.
- Public naming and compatibility-bridge behavior were left to earlier/later phases.

## Expected side effects

- `events.jsonl` may now contain `hook_route_redirected` entries with `from_route` / `to_route`.
- `trace.jsonl` `step_finished` records now include `candidate_route`, `final_route`, and `hook_route_redirects`; the legacy net `hook_route_override` summary remains populated when redirects occur.

## Validation performed

- `.venv/bin/python -m pytest tests/unit/test_validation.py`
- `.venv/bin/python -m pytest tests/contract/test_engine_contracts.py`
- `.venv/bin/python -m pytest tests/runtime/test_runtime_tracing.py`

## Deduplication / centralization

- Centralized hook-result normalization and redirect validation in `Engine._normalize_hook_result` so after-hooks and route-hooks share one contract and one redirect-event emission path.
