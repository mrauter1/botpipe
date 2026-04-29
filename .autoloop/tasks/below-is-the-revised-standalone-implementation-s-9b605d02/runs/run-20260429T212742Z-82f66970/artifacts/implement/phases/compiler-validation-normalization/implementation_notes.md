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
- `core.compiler.CompiledStep`
- `core.compiler.CompiledRoute`
- `core.compiler._compile_steps`
- `core.compiler._compile_routes`
- `core.compiler._compile_route`
- `core.compiler._topology_hash_payload`
- `core.engine.Engine`
- `runtime.static_graph.workflow_static_step_graph_payload`
- `runtime.static_graph.workflow_topology_payload`

## Checklist mapping

- Plan milestone 2 / AC-1:
  Compiled step metadata now uses canonical `kind`, `writes`, `producer_*`, `verifier_*`, `python_handler`, and route `required_writes`.
- Plan milestone 2 / AC-2:
  Simple workflows now reject class-level `transitions` and `flow`; simple `Workflow` defaults `Params`, and the canonical default session slot is `global`.
- Plan milestone 2 / AC-3:
  Simple default-route injection is step-kind specific, and route/control injection no longer applies the legacy provider-step contract to python/operation steps.
- Deliverables:
  Static graph/topology payload generation now reads from the canonical compiled shape and emits canonical session/state route fields.

## Assumptions

- The active implementation surface is the repo-root package tree (`core`, `runtime`, `autoloop`), even though it is currently untracked in git status during the package-layout migration.
- Provider payload field renames remain out of phase; the engine still emits some legacy provider-request keys while reading from canonical compiled metadata.

## Preserved invariants

- Low-level strict step classes remain usable as internal lowering scaffolding for this phase.
- `SUCCESS` is still accepted as an internal legacy destination token where older low-level workflows may still reference it, but compiled routes and topology artifacts normalize it to `FINISH`.
- Step-state storage still uses the existing engine/checkpoint mechanism.

## Intended behavior changes

- Public simple workflows must use step-local `routes` plus declaration order and optional `entry`; class-level `transitions` and `flow` now fail validation.
- The implicit/default session slot for compiled/simple workflows is now `global`.
- Compiled simple steps now surface canonical kinds: `step`, `produce_verify`, `python`, and `operation`.
- Static graph/topology outputs now emit canonical `writes`, `producer_writes`, `verifier_writes`, `required_writes`, and `global_session` fields.

## Known non-changes

- Low-level/core public cleanup is not finished in this phase; legacy internal class names and compatibility helpers still exist in the root `core` package.
- Provider request payload keys such as `route_infos` and `route_required_outputs` were not renamed yet.
- Item-state and step-item-state authoring APIs were not expanded in this phase.

## Expected side effects

- Existing tests or callers that still expect `pair`/`llm`/`system` compiled kinds or static-graph `produces`/`route_infos` payloads will need follow-up migration.
- Simple workflows that still declare `transitions` or `flow` will now fail at compile time instead of being silently lowered.

## Validation performed

- `python3 -m py_compile autoloop/simple.py core/routes.py core/sessions.py core/validation.py core/compiler.py core/engine.py runtime/static_graph.py`
- Runtime/unit pytest execution was not possible in this environment because `pytest`, `pydantic`, and related dependencies are unavailable.

## Deduplication / centralization

- Canonical route/session/static-graph naming is centralized off the compiled workflow shape rather than being re-expanded separately in static graph writers.
