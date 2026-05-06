# Original intent considered

- The immutable request snapshot remains the controlling spec. The raw phase log contains no later user clarification that narrows or relaxes the requested behavior.
- I compared that spec against the final codebase, phase implementation artifacts, test artifacts, decisions ledger, and focused runtime verification in the current workspace.

# Clarifications / superseding decisions

- The recorded decisions consistently preserve the requested migration shape:
  - compiled routes, not injected control routes, are the legality source
  - `ControlRoutes(question=...)` remains compatibility-only lowering to framework-default `Route.question()`
  - legacy top-level `question` / `reason` parsing remains accepted during migration, but canonical `outcome.route_fields` takes precedence
  - persisted inspection artifacts keep existing filenames and add compatibility fields instead of replacing them
- No authoritative clarification removed the request for route-schema-driven validation or backend schema delivery.

# Implemented behavior

- Route helpers, GLOBAL inheritance, step-local override/suppression, provider visibility modes, route payload schema modes, route-fields schemas, and additive inspection metadata are implemented in `autoloop/core/routes.py`, `autoloop/core/lowering.py`, `autoloop/core/compiler.py`, `autoloop/core/workflow_capabilities.py`, and `autoloop/runtime/static_graph.py`.
- Provider contracts now render and generate canonical `outcome.tag` / `outcome.payload` / `outcome.route_fields` schemas from compiled routes in `autoloop/core/outcome_contract.py`, `autoloop/core/engine_collaborators.py`, and `autoloop/core/providers/rendering.py`.
- Canonical parsing, legacy normalization, route legality checks, route-fields projection, and helper-route retry feedback are implemented in `autoloop/core/providers/parsing.py` and `autoloop/core/engine.py`.
- Docs and prompt surfaces now teach route helpers and canonical `outcome.route_fields`, and mark `ControlRoutes(question=...)` plus top-level `question` / `reason` as compatibility-only during migration in `Workflow_Instructions.md`, `docs/authoring.md`, and `docs/architecture.md`.
- The recorded test runs cover the main migration path, including:
  - `189 passed` for `tests/unit/test_validation.py`, `tests/unit/test_simple_surface.py`, and `tests/runtime/test_runtime_static_graph.py`
  - focused provider/parser/engine contract suites listed in the phase notes
  - my follow-up verification run: `49 passed, 232 deselected` for focused provider/static-graph/engine-contract cases

# Unresolved gaps

- `response_schema` is generated but not delivered to the current runtime transports.
  - Evidence: `ProviderContractBuilder` builds `response_schema` in `autoloop/core/engine_collaborators.py:169-182` and `:230-243`; `RenderedProviderTurn` carries it in `autoloop/core/providers/turns.py:19-31`; `RenderedLLMProvider` forwards it in `autoloop/core/providers/rendered.py:119-175`.
  - Evidence: the actual CLI transports only send `turn.prompt_text` and never use `turn.response_schema` in `autoloop/runtime/providers/codex.py:150-167, 218-233` and `autoloop/runtime/providers/claude.py:101-118, 154-167`.
  - Evidence: the implementation notes explicitly record this as a known non-change in `artifacts/implement/phases/provider-outcome-contract/implementation_notes.md`.
  - Why this is material: the request requires structured-output-capable providers to receive the generated schema, with schema fallback behavior reflected explicitly. Today the schema exists only as prompt/report metadata, not as an enforced backend contract.

- Raw JSON-schema route contracts can lose runtime validation entirely when `jsonschema` is unavailable.
  - Evidence: `_compile_route_contract()` falls back to `(schema, None)` when raw schema compilation hits the optional dependency path in `autoloop/core/compiler.py:1080-1094`.
  - Evidence: the current environment does not have `jsonschema` installed (`ModuleNotFoundError` from `./.venv/bin/python`).
  - Evidence: a live probe in this workspace compiled a route with `route_fields_schema={"required":["reason"],"properties":{"reason":{"type":"string"}},"additionalProperties":false}`; `compiled.routes["ask"]["done"].route_fields_validator` was `None`, and the engine still finished successfully when the scripted provider returned `route_fields={"reason": 123}`.
  - Why this is material: the request explicitly says runtime validation must not be weakened, and scripted/fake providers must validate against the same payload and route-fields schemas as rendered providers.

# Differences justified by later clarification or analysis

- Keeping `runtime_control_routes` and related inspection fields as additive compatibility views is justified by the run decisions because compiled routes remain the only legality source and existing artifact readers were explicitly kept compatible.
- Preserving `ControlRoutes(question=...)` only as lowering to framework-default `Route.question()` is justified by both the request and the recorded decisions; it does not reintroduce a second control-route subsystem.
- Preserving legacy top-level `question` / `reason` parsing during migration is justified by the request, and canonical `outcome.route_fields` precedence is correctly enforced.

# Recommended next run

- Complete end-to-end schema enforcement rather than revisiting the whole migration:
  - make route payload/route-fields JSON-schema mappings produce real runtime validators in all supported environments, or fail compilation clearly instead of silently degrading to metadata-only
  - deliver generated `response_schema` to provider transports/backends that support structured output, and make unsupported backends take an explicit documented fallback path
  - add regression coverage proving both rendered and scripted providers enforce custom raw JSON-schema route contracts, and proving structured-output-capable transports receive the canonical route-discriminated schema or its recorded simplified fallback
