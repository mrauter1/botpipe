# Test Strategy

- Task ID: this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0
- Pair: test
- Phase ID: route-contract-enforcement
- Phase Directory Key: route-contract-enforcement
- Phase Title: Fail-Closed Route Contracts
- Scope: phase-local producer artifact

## Behavior To Test Coverage Map
- AC-1 custom raw `payload_schema` fail-closed compile behavior:
  - `tests/unit/test_validation.py::test_validation_rejects_raw_route_payload_schema_without_jsonschema_dependency`
- AC-2 custom raw `route_fields_schema` fail-closed compile behavior:
  - `tests/unit/test_validation.py::test_validation_rejects_raw_route_fields_schema_without_jsonschema_dependency`
- AC-3 runtime rejection of invalid custom raw route payloads and route-fields for scripted and rendered providers:
  - `tests/contract/test_engine_contracts.py::test_scripted_provider_rejects_invalid_custom_raw_route_payload`
  - `tests/contract/test_engine_contracts.py::test_scripted_provider_rejects_invalid_custom_raw_route_fields`
  - `tests/contract/test_engine_contracts.py::test_rendered_provider_rejects_invalid_custom_raw_route_payload`
  - `tests/contract/test_engine_contracts.py::test_rendered_provider_rejects_invalid_custom_raw_route_fields`
- AC-4 helper-default compatibility and custom-override fail-closed behavior without `jsonschema`:
  - `tests/unit/test_validation.py::test_validation_allows_helper_default_route_fields_without_jsonschema_dependency`
  - `tests/unit/test_validation.py::test_validation_allows_helper_default_route_fields_without_jsonschema_dependency_after_named_target_resolution`
  - `tests/unit/test_validation.py::test_validation_rejects_custom_helper_route_fields_override_without_jsonschema_dependency`

## Preserved Invariants Checked
- Helper-generated `question` / `blocked` / `failed` route-fields contracts still compile without runtime JSON Schema validators only when the builtin handwritten engine validation is the semantic fallback.
- Named-target route normalization and internal route-copy paths do not strip helper-default fallback classification.
- Runtime enforcement remains strict once a fake validator is installed, for both scripted/fake and rendered providers.

## Edge Cases And Failure Paths
- Missing optional `jsonschema` dependency for custom raw route payload and route-fields mappings.
- Helper-default route with a named target exercises discovery/compiler route rewriting while preserving the helper fallback marker.
- Custom helper override expands the route-fields contract and must fail closed rather than silently inheriting the helper exception.

## Flake Risk And Stabilization
- Runtime contract tests use `ScriptedLLMProvider`, `RenderedLLMProvider`, and an in-process fake validator instead of external dependencies or network calls.
- Missing-`jsonschema` tests monkeypatch imports deterministically to avoid environment-sensitive package installation variance.

## Known Gaps
- Full-suite execution was not part of this phase turn; coverage remains focused on request-scoped compiler/runtime regressions and backend schema-delivery slices already exercised during implementation.
