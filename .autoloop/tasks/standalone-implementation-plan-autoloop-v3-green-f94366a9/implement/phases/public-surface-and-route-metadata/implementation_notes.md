# Implementation Notes

- Task ID: standalone-implementation-plan-autoloop-v3-green-f94366a9
- Pair: implement
- Phase ID: public-surface-and-route-metadata
- Phase Directory Key: public-surface-and-route-metadata
- Phase Title: Public surface and route metadata
- Scope: phase-local producer artifact

## Files changed
- `autoloop/simple.py`
- `autoloop/__init__.py`
- `core/__init__.py`
- `core/routes.py`
- `core/steps.py`
- `core/validation.py`
- `core/compiler.py`
- `core/engine.py`
- `core/providers/models.py`
- `core/providers/rendered.py`
- `core/providers/rendering.py`
- `core/providers/fake.py`
- `core/workflow_capabilities.py`
- `runtime/static_graph.py`
- `runtime/cli.py`
- `workflow/__init__.py`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_provider_boundary_core.py`
- `core/route_contracts.py` deleted
- `.autoloop/.../decisions.txt`

## Symbols touched
- Public surface: `AfterHookResult`, `Workflow`, `StrictWorkflow`, `step`, `review_step`, `system_step`, `workflow_step`, `WorkflowStep`, `Route`, `RouteInfo`
- Core route metadata: `RouteInfo`, `Route`, `normalize_route_spec`
- Core step model: `Step.route_infos`, `SystemStep.handler`, `WorkflowStep`
- Lowering/compiler: `_lower_simple_route_infos`, `normalize_step_route_metadata`, `_compile_system_handler`
- Provider/runtime payloads: `ProviderTurnContext`, `ProducerRequest`, `VerifierRequest`, `LLMRequest`, static graph and capability step payload builders

## Checklist mapping
- Plan milestone 1 / phase AC-1: removed `RouteContract` from `autoloop`, `core`, and `workflow` exports; deleted `core/route_contracts.py`; removed `route_contracts` from active step/compiler/provider plumbing touched in this phase.
- Plan milestone 1 / phase AC-2: finalized `RouteInfo` and `Route` validation; switched `Step` constructors to `route_infos`; added `SystemStep(handler=...)`; added core `WorkflowStep`; updated simple declaration signatures to the greenfield shape.
- Partial plan milestone 3 dependency cleanup: removed now-dead `route_contracts` and `route_required_artifacts` fields from provider/request/rendering payloads that would otherwise break after deleting the module.

## Assumptions
- `workflow/primitives.py` is a runtime primitive shim, not an authoring surface, so it can remain as-is in this phase without violating the "single active public authoring surface" goal.
- Bundled workflow package migration, loader discovery changes, and direct engine execution for `WorkflowStep` remain later-phase work per the phase contract.

## Preserved invariants
- Strict workflows still compile through `core.Workflow` and metaclass validation.
- Simple `Workflow` remains non-strict and keeps `EmptyState` as the default state model.
- Existing `on_<step>` handlers are still accepted for strict/core `SystemStep` declarations; simple `system_step(fn)` no longer requires them.

## Intended behavior changes
- `autoloop.simple` and `autoloop.__init__` now expose `AfterHookResult`.
- Simple `step(...)` and `review_step(...)` no longer accept `provider`, `model`, or `effort`.
- Core/public route metadata now validates/normalizes `summary`, `required_outputs`, and `handoff`.
- Simple `workflow_step(...)` lowers to a real core `WorkflowStep` instead of a generated `SystemStep` handler.

## Known non-changes
- No bundled workflow under `workflows/*` was migrated off legacy `route_contracts` in this phase.
- No direct engine execution path for `WorkflowStep` was added in this phase.
- `workflow/primitives.py` was not repurposed into a simple-authoring shim.

## Expected side effects
- Tests and downstream code that still assert `route_contracts` or import `RouteContract` from internal/public shims will need migration in later phases.
- Provider rendering and inspection payloads now rely only on `route_infos` plus `route_required_outputs`.

## Validation performed
- `python3 -m py_compile` on all touched Python modules and the updated unit tests.
- `rg` checks confirming `RouteContract` and `route_contracts` no longer appear in the touched public/core/runtime/provider export surfaces.

## Validation limits
- `pytest` could not run because `pytest` is not installed in this environment.
- Runtime import checks could not run because `pydantic` is not installed in this environment.

## Deduplication / centralization
- Centralized route metadata validation in `core/routes.py`.
- Centralized simple route-info lowering in `core/validation.py`.
- Centralized direct system-step return normalization in `core/compiler.py`.
