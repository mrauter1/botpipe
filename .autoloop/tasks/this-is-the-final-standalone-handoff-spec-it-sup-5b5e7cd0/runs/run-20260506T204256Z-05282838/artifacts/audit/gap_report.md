# Original intent considered

- `/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0/runs/run-20260506T204256Z-05282838/request.md`
- Required outcomes:
  - custom raw route `payload_schema` and `route_fields_schema` mappings must remain runtime-enforced in supported environments and must fail clearly instead of silently degrading when `jsonschema` is unavailable
  - structured-output-capable backends must receive the generated provider response schema, with an explicit documented fallback for unsupported backends
  - regression coverage must prove both raw-schema enforcement and backend schema delivery
  - existing `ControlRoutes(question=...)` lowering and legacy top-level `question` / `reason` parsing must remain compatible unless the fixes required otherwise

# Clarifications / superseding decisions

- No later raw-log clarification changed the user intent.
- `/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0/runs/run-20260506T204256Z-05282838/decisions.txt` records two material execution decisions that stay consistent with the request:
  - only helper-default `Route.question()` / `Route.blocked()` / `Route.failed()` route-fields contracts may use the existing handwritten engine fallback without `jsonschema`; custom raw route contracts must fail closed
  - native provider-schema delivery is currently supported only on Codex start turns; Codex resume and Claude stay on explicit `prompt_only` fallback because their observed command surfaces do not expose a native schema input

# Implemented behavior

- Fail-closed route-contract compilation is present in `autoloop/core/compiler.py`:
  - `_compile_route_contract(...)` now raises `WorkflowCompilationError` for raw route `payload_schema` and custom raw `route_fields_schema` mappings when the optional `jsonschema` dependency is unavailable
  - the only allowed missing-`jsonschema` exception is the helper-default route-fields path gated by `Route._handwritten_route_fields_validation_equivalent`
- Helper-route compatibility is preserved in `autoloop/core/routes.py`, `autoloop/core/discovery.py`, `autoloop/core/lowering.py`, and `autoloop/core/compiler.py`:
  - helper defaults set the internal fallback marker privately
  - `_replace_route(...)` preserves that marker across route rewrites so `ControlRoutes(question=...)` lowering and named-target normalization do not silently lose compatibility
- Runtime enforcement for raw schemas remains post-parse and strict:
  - engine validation paths in `autoloop/core/engine.py` still reject illegal payloads and route-fields
  - rendered and scripted provider regressions live in `tests/contract/test_engine_contracts.py`
- Provider response-schema delivery is wired into runtime transports:
  - `autoloop/runtime/providers/codex.py` writes the generated schema to a file and passes it via `codex exec --output-schema` on supported start turns
  - `autoloop/runtime/providers/_common.py` centralizes structured-output metadata
  - `autoloop/runtime/providers/claude.py` records explicit `prompt_only` fallback metadata because Claude has no observed native schema surface
- Documentation is explicit in `docs/authoring.md` and `controlroutes.md`:
  - delivery modes are documented as `native_full`, `native_simplified`, and `prompt_only`
  - fallback is documented as generation-only and not a relaxation of engine-side legality or schema validation
- Independent audit verification passed:
  - `.venv/bin/python -m pytest tests/unit/test_validation.py -k "raw_route_payload_schema_without_jsonschema_dependency or raw_route_fields_schema_without_jsonschema_dependency or helper_default_route_fields_without_jsonschema_dependency or custom_helper_route_fields_override_without_jsonschema_dependency"`
  - `.venv/bin/python -m pytest tests/contract/test_engine_contracts.py -k "invalid_custom_raw_route_payload or invalid_custom_raw_route_fields"`
  - `.venv/bin/python -m pytest tests/runtime/test_provider_backends.py -k "response_schema or prompt_only_fallback or output_schema_file or simplified_schema_delivery"`

# Unresolved gaps

- No material unresolved gaps found.

# Differences justified by later clarification or analysis

- The request asked for supported structured-output backends to receive the generated schema and for unsupported backends to keep an explicit documented fallback. The final code delivers native schema only on Codex start turns and records `prompt_only` fallback for Codex resume and Claude. That is justified by the recorded capability analysis in `decisions.txt` and remains consistent with the request because unsupported surfaces retain strict post-parse validation.
- The runtime raw-schema enforcement regressions install a fake validator in `tests/contract/test_engine_contracts.py` because the repository `.venv` does not include `jsonschema`. That is justified by the recorded implementation analysis and does not weaken product behavior; the default environment still compile-fails for custom raw route schemas.

# Recommended next run

- No follow-up implementation run is required for this request.
