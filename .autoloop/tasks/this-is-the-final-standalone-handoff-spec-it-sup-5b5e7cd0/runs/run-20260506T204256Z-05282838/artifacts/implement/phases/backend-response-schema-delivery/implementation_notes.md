# Implementation Notes

- Task ID: this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0
- Pair: implement
- Phase ID: backend-response-schema-delivery
- Phase Directory Key: backend-response-schema-delivery
- Phase Title: Backend Schema Delivery
- Scope: phase-local producer artifact

## Files changed
- `autoloop/runtime/providers/_common.py`
- `autoloop/runtime/providers/codex.py`
- `autoloop/runtime/providers/claude.py`
- `tests/runtime/test_provider_backends.py`
- `docs/authoring.md`
- `controlroutes.md`

## Symbols touched
- `structured_output_metadata(...)`
- `_CodexExecSurface.start_supports_output_schema`
- `_CodexExecSurface.resume_supports_output_schema`
- `CodexTransport.run_turn(...)`
- `build_codex_operation_executor(...)`
- `_prepare_turn_command(...)`
- `_prepare_structured_output(...)`
- `_write_response_schema_file(...)`
- `_cleanup_schema_file(...)`
- `_build_codex_result(...)`
- `ClaudeTransport.run_turn(...)`
- `build_claude_operation_executor(...)`
- `_structured_output_fallback(...)`
- `_build_claude_result(...)`

## Checklist mapping
- AC-1: `RenderedProviderTurn.response_schema` is passed through to Codex start turns via `--output-schema`.
- AC-2: `response_schema_simplified=True` records `native_simplified`, and the delivered schema remains the backend-facing payload.
- AC-3: Codex resume turns and Claude turns keep prompt-only generation but record explicit `prompt_only` structured-output fallback metadata.
- AC-4: `docs/authoring.md` and `controlroutes.md` describe native full delivery, simplified delivery, prompt-only fallback, and the invariant that fallback does not relax engine-side validation.

## Assumptions
- Codex native structured output is limited to CLI surfaces that advertise `--output-schema`.
- Claude CLI does not currently expose a native response-schema input surface.

## Preserved invariants
- Backend fallback changes provider-side generation guidance only.
- Route legality, payload validation, and route-fields validation remain enforced post-parse by the engine.
- Existing `ControlRoutes(question=...)` lowering and legacy top-level `question` / `reason` compatibility remain unchanged.

## Intended behavior changes
- Runtime provider metadata now exposes an explicit structured-output delivery record for rendered-provider turns.
- Codex start turns receive the generated schema natively when supported; resume and unsupported backends record prompt-only fallback instead of silently relying on prompt text alone.

## Known non-changes
- No new provider abstraction layer was introduced.
- No native response-schema delivery was added for Claude beyond explicit fallback recording.
- No runtime validation paths were relaxed.

## Expected side effects
- Codex runs with native schema delivery write run-scoped schema files under `provider_response_schemas/codex/` when a run folder exists.
- Runtime metadata now includes `structured_output` records that downstream tooling can inspect.

## Validation performed
- `.venv/bin/python -m pytest tests/runtime/test_provider_backends.py -k "response_schema or prompt_only_fallback or output_schema_file or simplified_schema_delivery"`
- `.venv/bin/python -m pytest tests/contract/test_engine_contracts.py -k "invalid_custom_raw_route_payload or invalid_custom_raw_route_fields"`
- `.venv/bin/python -m pytest tests/unit/test_validation.py -k "raw_route_payload_schema_without_jsonschema_dependency or raw_route_fields_schema_without_jsonschema_dependency or helper_default_route_fields_without_jsonschema_dependency or custom_helper_route_fields_override_without_jsonschema_dependency"`

## Deduplication / centralization
- Structured-output delivery metadata stays centralized in `autoloop/runtime/providers/_common.py` so supported and fallback backends report one stable shape.
