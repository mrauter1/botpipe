# Route-Schema Enforcement Completion Plan

## Scope
- Complete the remaining standalone-handoff migration work for route-local JSON-schema enforcement and provider response-schema delivery.
- Keep scope local to compiled route contracts, outcome validation, rendered-provider transport plumbing, backend observability, and regression coverage.
- Do not change unrelated artifact-schema, pending-input, or workflow-topology behavior.

## Milestone 1: Restore fail-closed route-contract enforcement
- Touchpoints:
  - `autoloop/core/compiler.py`: stop treating custom raw route `payload_schema` / `route_fields_schema` mappings as metadata-only when `jsonschema` is unavailable.
  - `autoloop/core/engine.py`: keep route legality, payload validation, and route-fields validation on the existing post-parse path; do not loosen retry/error classification.
  - `autoloop/core/routes.py` and any shared helper used to distinguish helper-generated default route-fields semantics from custom raw mappings.
- Intended behavior:
  - Explicit raw route `payload_schema` mappings must either compile a runtime validator or fail compilation with a clear dependency error.
  - Explicit raw custom `route_fields_schema` mappings must either compile a runtime validator or fail compilation with a clear dependency error.
  - Built-in helper-generated default route-fields semantics for question/blocked/failed routes may continue to use the engine's handwritten validation only when that fallback is semantically equivalent to the effective route contract.
  - Custom helper overrides must not inherit the helper exception; if a route author supplies a broader or different raw `route_fields_schema`, that mapping must compile a validator or fail clearly.
- Regression coverage:
  - Add compile/validation coverage for missing-`jsonschema` custom route contracts so the failure mode is explicit instead of silent.
  - Add runtime contract tests showing invalid custom route payloads and invalid custom route-fields fail for both `ScriptedLLMProvider` and `RenderedLLMProvider`.
  - Add missing-`jsonschema` regression coverage proving helper-generated default question/blocked/failed route-fields contracts remain compatible, while custom helper overrides fail closed instead of slipping onto the handwritten path.

## Milestone 2: Deliver provider response schemas to backends and record fallback
- Touchpoints:
  - `autoloop/core/providers/rendered.py` and `autoloop/core/providers/turns.py`: keep `RenderedProviderTurn.response_schema` and `response_schema_simplified` as the transport source of truth.
  - `autoloop/runtime/providers/codex.py` and `autoloop/runtime/providers/claude.py`: consume the rendered schema when the backend capability surface supports native structured output; otherwise emit an explicit prompt-only fallback record.
  - `docs/authoring.md` and `controlroutes.md`: document native-schema delivery, simplified-schema delivery, and unsupported-backend prompt-only fallback as part of the runtime control-contract surface.
  - Provider/backend tests under `tests/runtime/test_provider_backends.py` and contract coverage for rendered-provider turns.
- Intended behavior:
  - Structured-output-capable backends receive the exact generated provider outcome schema from `build_provider_outcome_schema(...)`.
  - If the generated schema was simplified for provider limits, the simplified schema is what gets delivered and that fact stays observable.
  - Unsupported backends may keep prompt-text guidance only, but the transport/result metadata must record that provider-side structured output was unavailable.
  - No provider-side fallback may relax engine-side route legality, payload validation, or route-fields validation.
- Observability contract:
  - Backend execution metadata must expose a stable structured-output delivery record that distinguishes at least:
    - native full canonical schema delivered
    - native simplified schema delivered
    - prompt-only fallback because backend support was unavailable
  - Tests should assert against that record or the backend request surface directly, not just prompt text.
  - The same three delivery modes must be documented in the authoritative authoring/runtime docs, together with the invariant that backend fallback never weakens engine-side route legality, payload validation, or route-fields validation.

## Interfaces And File Ownership
- `CompiledRoute` contract:
  - `payload_validator` and `route_fields_validator` must never be absent for custom raw mappings that require runtime schema enforcement.
  - `None` remains acceptable only for routes whose validation is intentionally covered by existing handwritten engine checks.
- Rendered provider contract:
  - `RenderedProviderTurn.response_schema` remains the canonical backend-facing schema payload.
  - `RenderedProviderTurn.response_schema_simplified` remains the explicit indicator that provider-side delivery used the simplified fallback schema, not the full discriminated form.
- Backend integration:
  - Keep transport protocol shape stable; prefer local backend-specific handling over introducing a new provider abstraction layer.
  - Any new backend capability probe should extend existing help-surface/capability detection instead of bypassing it.

## Compatibility Notes
- Preserve `ControlRoutes(question=...)` lowering exactly as today.
- Preserve legacy top-level `question` / `reason` parsing as a compatibility input path, while keeping canonical `outcome.route_fields` authoritative when both are present.
- Preserve helper-generated default question/blocked/failed route-fields behavior in environments without `jsonschema`; only custom raw route-schema authoring should tighten to explicit compile-fail when runtime validation cannot be guaranteed.
- Do not change prompt rendering semantics except for documented structured-output fallback messaging if backend support is absent.
- The only intentional behavior tightening is fail-closed handling for custom raw route schema mappings that would otherwise lose runtime enforcement.

## Validation Plan
- `tests/unit/test_validation.py` or nearby compiler validation tests:
  - missing `jsonschema` + custom raw route `payload_schema`
  - missing `jsonschema` + custom raw route `route_fields_schema`
  - missing `jsonschema` + helper-generated default question/blocked/failed route-fields contracts still compile through the handwritten-compatible path
  - missing `jsonschema` + custom helper `route_fields_schema` override fails closed instead of using helper fallback
- `tests/contract/test_engine_contracts.py`:
  - scripted provider rejects invalid custom route payload
  - scripted provider rejects invalid custom route-fields
  - rendered provider rejects invalid custom route payload
  - rendered provider rejects invalid custom route-fields
- `tests/runtime/test_provider_backends.py`:
  - supported backend path receives `turn.response_schema`
  - simplified schema path is delivered and recorded
  - unsupported backend path records prompt-only fallback without changing runtime post-parse enforcement
- `docs/authoring.md` and `controlroutes.md`:
  - describe supported native structured-output delivery, simplified-schema fallback delivery, and unsupported-backend prompt-only fallback
  - state that fallback changes provider-side guidance only; engine-side legality and schema validation remain strict

## Risk Register
- Risk: treating all raw route-fields mappings as unsupported without `jsonschema` would break built-in helper routes in environments that currently rely on handwritten validation.
  - Mitigation: explicitly classify helper-generated defaults versus custom overrides and add regression coverage for both paths.
- Risk: backend schema pass-through could fork behavior between providers and prompt-only execution.
  - Mitigation: keep post-parse engine validation authoritative and add metadata-backed tests for delivery mode.
- Risk: transport changes could become backend-specific sprawl.
  - Mitigation: keep the shared contract at `RenderedProviderTurn`; limit implementation differences to capability detection and request assembly inside each backend module.

## Rollback
- Revert backend request-plumbing changes independently from route-contract enforcement if provider integration proves unstable.
- Do not roll back the fail-closed route-contract change without replacing it with equivalent runtime validation; silent metadata-only weakening is not an acceptable rollback target.
