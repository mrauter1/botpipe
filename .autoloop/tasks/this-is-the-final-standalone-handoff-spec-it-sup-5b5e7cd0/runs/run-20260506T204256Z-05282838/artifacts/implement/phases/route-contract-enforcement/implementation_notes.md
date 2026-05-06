# Implementation Notes

- Task ID: this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0
- Pair: implement
- Phase ID: route-contract-enforcement
- Phase Directory Key: route-contract-enforcement
- Phase Title: Fail-Closed Route Contracts
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/routes.py`
- `autoloop/core/compiler.py`
- `autoloop/runtime/providers/_common.py`
- `autoloop/runtime/providers/codex.py`
- `autoloop/runtime/providers/claude.py`
- `tests/unit/test_validation.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_provider_backends.py`
- `docs/authoring.md`
- `controlroutes.md`

## Symbols touched
- `Route._handwritten_route_fields_validation_equivalent`
- `_with_handwritten_route_fields_validation_equivalent(...)`
- `Route.question()`
- `Route.blocked()`
- `Route.failed()`
- `_compile_route_contract(...)`
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
- `_patch_missing_jsonschema(...)`
- `_install_fake_jsonschema_validator(...)`

## Checklist mapping
- Milestone 1 / AC-1 / AC-2: done via fail-closed `_compile_route_contract(...)` and helper-default route marker gating.
- Milestone 1 / AC-3: done via scripted and rendered engine regressions for invalid custom raw payload and route-fields outcomes.
- Milestone 1 / AC-4: done via missing-`jsonschema` validation tests for helper defaults versus custom helper overrides.
- Milestone 2: done as an intentional adjacent change because it is part of the authoritative request and global plan artifact, even though the active phase acceptance criteria focus on route-contract enforcement.

## Assumptions
- The repository `.venv` does not include the optional `jsonschema` dependency; default runtime behavior for custom raw route schemas therefore remains compile-fail.
- Codex CLI capability probing is the runtime source of truth for native response-schema delivery support.

## Preserved invariants
- Legacy `ControlRoutes(question=...)` lowering and legacy top-level `question` / `reason` parsing were left unchanged.
- Helper-default `question` / `blocked` / `failed` route-fields semantics still work without `jsonschema` only where the existing handwritten engine validation is semantically equivalent.
- Prompt-only backend fallback does not relax engine-side route legality, payload validation, or route-fields validation.

## Intended behavior changes
- Custom raw route `payload_schema` mappings no longer degrade to metadata-only when `jsonschema` is unavailable; they now fail compilation clearly.
- Custom raw route `route_fields_schema` mappings no longer degrade to metadata-only when `jsonschema` is unavailable; only helper-default question/blocked/failed route-fields may fall back to handwritten engine validation.
- Codex start turns now deliver provider response schemas through `--output-schema` and record native full versus native simplified delivery in metadata.
- Claude and unsupported Codex resume surfaces now record explicit prompt-only structured-output fallback metadata.

## Known non-changes
- No changes were made to artifact-schema validation, pending-input schema validation, or unrelated workflow validation behavior.
- No backend-side structured-output delivery was added for Claude because the observed CLI surface does not expose a native response-schema input.

## Expected side effects
- Runs that author custom raw route schemas now require the optional `jsonschema` dependency at compile time.
- Codex native structured-output turns may leave run-scoped schema files under `provider_response_schemas/codex/`.
- The dedicated runtime contract regressions now rely on `tests/contract/test_engine_contracts.py` remaining tracked in git state instead of being recreated ad hoc in an untracked worktree file.

## Validation performed
- `python3 -m compileall autoloop/core/routes.py autoloop/core/compiler.py autoloop/runtime/providers/_common.py autoloop/runtime/providers/codex.py autoloop/runtime/providers/claude.py tests/unit/test_validation.py tests/contract/test_engine_contracts.py tests/runtime/test_provider_backends.py`
- `.venv/bin/python -m pytest tests/unit/test_validation.py -k "raw_route_payload_schema_without_jsonschema_dependency or raw_route_fields_schema_without_jsonschema_dependency or helper_default_route_fields_without_jsonschema_dependency or custom_helper_route_fields_override_without_jsonschema_dependency"`
- `.venv/bin/python -m pytest tests/contract/test_engine_contracts.py -k "invalid_custom_raw_route_payload or invalid_custom_raw_route_fields"`
- `.venv/bin/python -m pytest tests/runtime/test_provider_backends.py -k "response_schema or prompt_only_fallback or output_schema_file or simplified_schema_delivery"`

## Deduplication / centralization
- Shared structured-output delivery metadata was centralized in `autoloop/runtime/providers/_common.py` so Codex and Claude fallbacks report one stable metadata shape.
- Helper-route compatibility bookkeeping now stays inside `autoloop/core/routes.py` rather than leaking a compiler flag through the public `Route.to(...)` constructor signature.
