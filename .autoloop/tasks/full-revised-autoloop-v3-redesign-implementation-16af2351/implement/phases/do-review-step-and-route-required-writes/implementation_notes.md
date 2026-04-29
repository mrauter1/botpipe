# Implementation Notes

- Task ID: full-revised-autoloop-v3-redesign-implementation-16af2351
- Pair: implement
- Phase ID: do-review-step-and-route-required-writes
- Phase Directory Key: do-review-step-and-route-required-writes
- Phase Title: Do review step and route required writes
- Scope: phase-local producer artifact

## Files Changed

- `autoloop/simple.py`
- `core/routes.py`
- `core/steps.py`
- `core/validation.py`
- `core/compiler.py`
- `core/engine.py`
- `runtime/static_graph.py`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_validation.py`
- `tests/contract/test_engine_contracts.py`

## Symbols Touched

- `ReviewStepDeclaration`, `review_step`, `do_review_step`
- `Route`, `Route.to`, `Route.complete`, `Route.pause`, `Route.fail`
- `PairStep`
- `normalize_step_route_metadata`, `_lower_simple_default_routes`, `_merge_transition_tables`
- `CompiledStep`, `_compile_steps`
- `Engine._execute_pair_step`, `Engine._run_pair_step`, `Engine._required_output_artifacts`
- `workflow_static_step_graph_payload`, `workflow_topology_payload`

## Checklist Mapping

- Phase 2 canonical API: added `do_review_step` support for `review_requires`, `review_writes`, `routes`, and `review_session`; kept `review_step` compatibility.
- Phase 2 compiled/runtime metadata: lowered pair-step do/review artifacts and review-session metadata into compiled steps and topology payloads.
- Phase 2 provider/runtime contract split: producer contract now uses do-phase requires/writes only; verifier contract now uses review-phase requires/writes and route-required-write metadata.
- Phase 2 selected-route required writes: preserved centralized artifact validation while adding explicit-empty override semantics.
- Deferred in this phase: separate do/review lifecycle hook slots and broader public context/state work remain for later phases.

## Assumptions

- Review-session overrides use declared workflow `Session` slots; inline `Session.fresh()` style helpers are not introduced in this phase.
- Existing strict `PairStep` workflows should keep legacy behavior when no review-specific metadata is supplied: producer/verifier both still see the legacy writable union.

## Preserved Invariants

- Pair-step execution still lowers into the existing compiled FSM and retry loop.
- Final selected-route artifact validation remains centralized in the engine after outcome handling.
- Legacy `review_step`, `producer`/`verifier`, and `required_outputs` compatibility paths remain accepted.

## Intended Behavior Changes

- Canonical `do_review_step` can now declare separate review-only preconditions, writable artifacts, custom routes, and review-session overrides.
- Producer and verifier provider contracts are now intentionally different for pair steps.
- Explicit `required_writes=[]` now suppresses artifact-level required defaults for that selected route.
- Injected simple default routes no longer override or conflict with explicit transition declarations.

## Known Non-Changes

- Pair-step before/after hooks remain the existing shared hook surface; phase-specific hook slots were not added here.
- Route/on-taken hook execution model, state descriptors, and session mutation helpers remain out of scope for this phase.
- Legacy serialized field names such as `producer_prompt`, `verifier_prompt`, and `route_required_outputs` remain present; new review metadata was added additively.

## Expected Side Effects

- Provider-facing tests that asserted producer-turn route metadata were updated to the new split contract.
- Static topology/static-graph payloads now expose additive `do_prompt`/`review_prompt`, `review_requires`, `review_writes`, and `review_session_name` fields.

## Validation Performed

- `python3 -m py_compile autoloop/simple.py core/routes.py core/steps.py core/validation.py core/compiler.py core/engine.py runtime/static_graph.py runtime/cli.py core/workflow_capabilities.py`
- `./.venv/bin/python -m pytest tests/unit/test_simple_surface.py tests/unit/test_validation.py tests/contract/test_engine_contracts.py tests/runtime/test_runtime_static_graph.py -q`
- `./.venv/bin/python -m pytest tests/unit/test_provider_boundary_core.py tests/runtime/test_compatibility_runtime.py -q`

## Deduplication / Centralization

- Kept route-required-write enforcement in `Engine._required_output_artifacts` instead of introducing a pair-step-only validator.
- Kept artifact inventory/qualified-name resolution centralized in `core.validation` and `core.compiler`; pair-step phase metadata only narrows contract rendering at the edge.
