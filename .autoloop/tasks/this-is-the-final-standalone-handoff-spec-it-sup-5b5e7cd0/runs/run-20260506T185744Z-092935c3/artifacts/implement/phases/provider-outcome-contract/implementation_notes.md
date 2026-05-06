# Implementation Notes

- Task ID: this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0
- Pair: implement
- Phase ID: provider-outcome-contract
- Phase Directory Key: provider-outcome-contract
- Phase Title: Canonical Provider Outcomes
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/engine.py`
- `autoloop/core/providers/rendering.py`
- `tests/runtime/test_runtime_providers.py`
- `tests/unit/test_provider_boundary_core.py`
- `tests/unit/test_provider_retries.py`
- `tests/contract/test_engine_contracts.py`

## Symbols touched
- `Engine._validate_outcome`
- `Engine._validate_outcome_route_fields`
- `render_provider_turn`
- `_render_outcome_response`
- `_route_payload_schema`
- `build_retry_feedback`
- `parse_outcome_json`

## Checklist mapping
- Phase 2 / provider contract rendering: canonical `outcome.tag` / `outcome.payload` / `outcome.route_fields` prompt contract rendered from compiled-route metadata.
- Phase 2 / parsing normalization: canonical envelope parsing plus canonical-over-legacy precedence locked by runtime-provider tests.
- Phase 2 / engine validation: legacy direct `Outcome(question=..., reason=...)` inputs normalize through `route_fields` before compiled-route validation.

## Assumptions
- Keeping the `### Control response` heading is acceptable as a compatibility label because the body now teaches only the canonical `outcome` envelope.
- Structured provider transports can adopt `RenderedProviderTurn.response_schema` later; this phase keeps runtime validation authoritative even where transports still consume prompt text only.

## Preserved invariants
- Compiled provider-visible routes remain the only legality source.
- Route finalization, after hooks, required-write enforcement, and handoff scheduling stay on the existing engine path.
- Legacy top-level `tag` / `payload` / `question` / `reason` inputs remain accepted during migration.

## Intended behavior changes
- Provider prompts now teach the canonical `outcome` envelope and route-specific `route_fields` usage.
- Canonical `outcome.route_fields` wins over legacy top-level question/reason when both are present.
- Direct/scripted provider outcomes with legacy `question`/`reason` normalize into `route_fields` before validation.

## Known non-changes
- Provider transports still primarily consume rendered prompt text; transport-side structured-schema enforcement was not introduced in this phase.
- This slice did not update docs, compile reports, static graph payloads, or topology hashing.

## Expected side effects
- Retry feedback now points providers toward `outcome.route_fields.questions` instead of top-level `question`.
- Plain authored `blocked`/`failed` tags keep nullable-reason compatibility even without helper presets.

## Validation performed
- `python3 -m py_compile autoloop/core/outcome_contract.py autoloop/core/providers/parsing.py autoloop/core/providers/rendering.py autoloop/core/engine.py autoloop/core/engine_collaborators.py autoloop/core/primitives.py`
- `./.venv-autoloop/bin/python -m pytest -q tests/unit/test_provider_boundary_core.py tests/unit/test_provider_retries.py tests/unit/test_primitives_and_stores.py tests/runtime/test_runtime_providers.py`
- `./.venv-autoloop/bin/python -m pytest -q tests/contract/test_engine_contracts.py -k 'malformed_provider_output or illegal_route or pause_skips_handler'`
- `./.venv-autoloop/bin/python -m pytest -q tests/contract/test_engine_contracts.py -k 'question_route_requires_question_field or provider_invalid_question_retries_and_recovers or rendered_provider_invalid_question_retries_and_recovers or explicit_blocked_and_failed_routes_do_not_require_reason_field or rendered_provider_matches_direct_reason_optional_behavior_for_explicit_blocked_and_failed_routes or provider_question_route_is_illegal_in_full_auto_mode or rendered_provider_question_route_is_illegal_in_full_auto_mode or provider_invalid_question_retry_exhaustion_marks_failure_context or rendered_provider_invalid_question_retry_exhaustion_marks_failure_context or system_question_events_validate_strictly_and_failed_remains_authored or llm_step_retries_invalid_payload_twice_and_succeeds_on_third_attempt'`
- `./.venv-autoloop/bin/python -m pytest -q tests/runtime/test_runtime_providers.py -k 'parse_outcome_json_accepts_canonical_outcome_envelope or parse_outcome_json_prefers_canonical_route_fields_over_legacy_top_level_fields'`
- `./.venv-autoloop/bin/python -m pytest -q tests/unit/test_provider_boundary_core.py tests/unit/test_provider_retries.py tests/unit/test_primitives_and_stores.py tests/runtime/test_runtime_providers.py tests/contract/test_engine_contracts.py -k 'question or blocked or failed or invalid_payload or illegal_route or malformed_provider_output or render_provider_turn_renders_markdown_contract_without_raw_output or parses_codex_verifier_outcome_in_core or middleware_pause_skips_handler'`

## Deduplication / centralization
- Centralized canonical-route normalization and schema language around the provider rendering/engine validation path instead of reintroducing tag-specific control handling in each caller.
