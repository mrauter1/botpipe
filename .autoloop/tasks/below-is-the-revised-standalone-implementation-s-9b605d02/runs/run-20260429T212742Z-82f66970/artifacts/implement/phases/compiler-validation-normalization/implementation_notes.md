# Implementation Notes

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: implement
- Phase ID: compiler-validation-normalization
- Phase Directory Key: compiler-validation-normalization
- Phase Title: Compiler And Validation Canonicalization
- Scope: phase-local producer artifact

## Files changed

- `autoloop/simple.py`
- `core/routes.py`
- `core/sessions.py`
- `core/validation.py`
- `core/compiler.py`
- `core/context.py`
- `core/engine.py`
- `runtime/static_graph.py`
- `tests/unit/test_simple_surface.py`
- `tests/runtime/test_runtime_static_graph.py`

## Symbols touched

- `core.sessions.DEFAULT_SESSION_NAME`
- `core.routes.Route`
- `core.validation.describe_workflow_class`
- `core.validation._lower_simple_workflow_graph`
- `core.validation._lower_simple_default_routes`
- `core.validation._inject_reserved_routes`
- `core.validation._lower_simple_steps`
- `core.validation.normalize_step_route_metadata`
- `core.compiler.CompiledStep`
- `core.compiler.CompiledRoute`
- `core.compiler._compile_steps`
- `core.compiler._compile_routes`
- `core.compiler._compile_route`
- `core.compiler._topology_hash_payload`
- `core.context.Context.step_state`
- `core.context.Context.item_state`
- `core.context.Context.step_item_state`
- `core.engine.Engine`
- `core.engine.Engine._ensure_step_state_store`
- `core.engine.Engine._serialize_step_states`
- `runtime.static_graph.workflow_static_step_graph_payload`
- `runtime.static_graph.workflow_topology_payload`

## Checklist mapping

- Plan milestone 2 / AC-1:
  Compiled step metadata now uses canonical `kind`, `writes`, `producer_*`, `verifier_*`, `python_handler`, and route `required_writes`.
- Plan milestone 2 / AC-2:
  Simple workflows now reject class-level `transitions` and `flow`; simple `Workflow` defaults `Params`, and the canonical default session slot is `global`.
- Plan milestone 2 / AC-3:
  Simple default-route injection is step-kind specific, route/control injection no longer applies the legacy provider-step contract to python/operation steps, simple step state is runtime model-backed, and incomplete item-state public access is suppressed.
- Deliverables:
  Static graph/topology payload generation now reads from the canonical compiled shape and emits canonical session/state route fields, while route normalization and checkpoint state handling now flow through canonical `Route` and Pydantic step-state metadata.

## Assumptions

- The active implementation surface is the repo-root package tree (`core`, `runtime`, `autoloop`), even though it is currently untracked in git status during the package-layout migration.
- Provider payload field renames remain out of phase; the engine still emits some legacy provider-request keys while reading from canonical compiled metadata.

## Preserved invariants

- Low-level strict step classes remain usable as internal lowering scaffolding for this phase.
- `SUCCESS` is still accepted as an internal legacy destination token where older low-level workflows may still reference it, but compiled routes and topology artifacts normalize it to `FINISH`.
- Workflow state and params remain Pydantic models end-to-end.

## Intended behavior changes

- Public simple workflows must use step-local `routes` plus declaration order and optional `entry`; class-level `transitions` and `flow` now fail validation.
- The implicit/default session slot for compiled/simple workflows is now `global`.
- Compiled simple steps now surface canonical kinds: `step`, `produce_verify`, `python`, and `operation`.
- Static graph/topology outputs now emit canonical `writes`, `producer_writes`, `verifier_writes`, `required_writes`, and `global_session` fields.
- Canonical `Route` helpers no longer accept `required_outputs`, no longer expose `Route.complete`, and no longer special-case `SUCCESS` at the route helper layer.
- Simple step `state=BaseModelSubclass` is stored as a real model at runtime and serialized back to checkpoint payloads on save/resume.
- `item.state` and `step_name.item_state` prompt placeholders are rejected on the simple surface until a model-backed item-state authoring path exists.

## Known non-changes

- Low-level/core public cleanup is not finished in this phase; legacy internal class names and compatibility helpers still exist in the root `core` package.
- Provider request payload keys such as `route_infos` and `route_required_outputs` were not renamed yet.
- Item-state and step-item-state authoring APIs were not expanded in this phase; instead, the incomplete public context accessors are suppressed unless a model-backed implementation exists.

## Expected side effects

- Existing tests or callers that still expect `pair`/`llm`/`system` compiled kinds or static-graph `produces`/`route_infos` payloads will need follow-up migration.
- Simple workflows that still declare `transitions` or `flow` will now fail at compile time instead of being silently lowered.
- Callers that still use `Route.complete(...)` or `Route.to(..., required_outputs=...)` now fail fast and must migrate to `Route.finish(...)` and `required_writes=...`.

## Validation performed

- `python3 -m py_compile autoloop/simple.py core/routes.py core/sessions.py core/validation.py core/compiler.py core/engine.py runtime/static_graph.py`
- `python3 -m py_compile autoloop/simple.py core/routes.py core/validation.py core/compiler.py core/context.py core/engine.py runtime/static_graph.py tests/unit/test_simple_surface.py tests/runtime/test_runtime_static_graph.py`
- Runtime/unit pytest execution was not possible in this environment because `pytest`, `pydantic`, and related dependencies are unavailable.

## Deduplication / centralization

- Canonical route metadata now centralizes through `normalize_step_route_metadata()` returning `Route` objects, so compiler/topology writers do not rebuild per-route summary/write metadata separately.
- Checkpoint serialization for simple step state is centralized through `Engine._serialize_step_states()` so runtime state can stay model-backed while persisted payloads remain filesystem-safe dicts.
