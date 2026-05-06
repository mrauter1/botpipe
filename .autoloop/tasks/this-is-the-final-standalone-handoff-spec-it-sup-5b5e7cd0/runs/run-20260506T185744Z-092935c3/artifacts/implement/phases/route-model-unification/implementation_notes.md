# Implementation Notes

- Task ID: this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0
- Pair: implement
- Phase ID: route-model-unification
- Phase Directory Key: route-model-unification
- Phase Title: Unify Route Metadata
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/routes.py`
- `autoloop/core/discovery.py`
- `autoloop/core/lowering.py`
- `autoloop/core/topology.py`
- `autoloop/core/compiler.py`
- `autoloop/core/workflow_capabilities.py`
- `autoloop/runtime/static_graph.py`
- `tests/unit/test_validation.py`
- `tests/unit/test_simple_surface.py`
- `tests/runtime/test_runtime_static_graph.py`
- `.../decisions.txt`

## Symbols touched
- `Route`
- `WorkflowDefinition`
- `ResolvedRouteSpec`
- `CompiledRoute`
- `CompiledWorkflow.route`
- `_compile_routes`
- `_compile_global_routes`
- `_compile_route`
- `_compiled_provider_visibility`
- `_effective_provider_visibility`
- `_compile_route_contract`
- `step_available_route_tags`
- `step_runtime_control_route_tags`
- `resolve_step_routes`
- `normalize_step_route_metadata`
- `validate_control_contracts`
- `_validate_route_destination`
- `WorkflowRouteCapability`
- `_topology_route_payload`
- `_internal_route_payload`

## Checklist mapping
- Plan Phase 1 / route metadata model: completed via helper constructors, visibility normalization, payload-schema mode, route-fields schema, preset kind, and disabled support on `Route` / `CompiledRoute`.
- Plan Phase 1 / replace injected runtime-control legality: completed via precedence-based `resolve_step_routes()` and compiler use of compiled routes only.
- Plan Phase 1 / `ControlRoutes(question=...)` lowering: completed via framework-default `Route.question()` lowering with derived compatibility labels.
- Plan Phase 3 inspection alignment (additive only): partially completed by adding compiled route metadata to workflow capability and static graph payloads; broader report/hash/schema surfaces remain for later phases.

## Assumptions
- This phase keeps legacy `runtime_control_routes` / `is_runtime_control` only as derived compatibility views because downstream inspection/tests still read them.
- Optional `jsonschema` may be absent in local environments, so built-in helper route-field schemas must still compile as metadata without validator construction.

## Preserved invariants
- Route legality still flows through compiled step/global route tables plus `available_routes` / provider-visible route lists.
- Existing route finalization ordering, hook execution order, and child-workflow/branch-group execution paths were not redesigned.
- Explicit `GLOBAL` routes still remain separately inspectable while step-local routes override them by tag.

## Intended behavior changes
- `ControlRoutes(question=...)` no longer injects runtime topology; it lowers to framework-default helper routes used only through compiled route resolution.
- `Route.question()`, `Route.blocked()`, `Route.failed()`, `Route.hidden()`, and `Route.disabled()` now exist and stamp route metadata directly.
- `CompiledRoute` now carries provider visibility mode, payload-schema mode, route-fields schema, preset kind, inheritance source, and disabled state.
- Step-local `Route.disabled()` suppresses inherited `GLOBAL`/framework-default routes before available/provider-visible route sets are computed.
- Compatibility-lowered question routes now use explicit empty `required_writes`, so inspection output shows `none (explicit)` instead of inherited writes for that helper route.

## Known non-changes
- Provider parsing, canonical `outcome.route_fields`, runtime `Outcome.route_fields`, and provider-schema generation were not implemented in this phase.
- Compile report / route table wording still uses `runtime-control` compatibility labels rather than the final helper/inheritance terminology.
- Raw authored `blocked` / `failed` tags do not gain helper semantics from tag name alone; helper behavior comes from helper metadata or question-tag legacy compatibility only.

## Expected side effects
- Topology/capability/static-graph payloads now expose additive route metadata fields such as `provider_visibility`, `preset_kind`, `inheritance_source`, `disabled`, and route-fields schema.
- Route-topology hashing now changes when helper metadata, visibility mode, schema metadata, inheritance source, or suppression state changes.

## Validation performed
- `python3 -m py_compile autoloop/core/routes.py autoloop/core/discovery.py autoloop/core/lowering.py autoloop/core/topology.py autoloop/core/compiler.py`
- `python3 -m py_compile autoloop/core/workflow_capabilities.py autoloop/runtime/static_graph.py`
- `.venv/bin/python -m pytest -q tests/unit/test_validation.py tests/unit/test_simple_surface.py tests/runtime/test_runtime_static_graph.py`
  - Result: `189 passed`, `14 warnings` (pre-existing Pydantic field-name shadow warnings in workflow contract fixtures)

## Deduplication / centralization
- Centralized precedence and compatibility lowering in `resolve_step_routes()` so discovery, lowering, and compiler no longer duplicate runtime-control injection logic.
- Reused the existing schema compilation helper for route metadata where possible, with a metadata-only fallback when the optional `jsonschema` dependency is unavailable.
