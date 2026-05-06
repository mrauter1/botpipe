# Test Strategy

- Task ID: this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0
- Pair: test
- Phase ID: route-model-unification
- Phase Directory Key: route-model-unification
- Phase Title: Unify Route Metadata
- Scope: phase-local producer artifact

## Behavior-to-test coverage
- Compiled step route tables are the authority for legality metadata:
  covered by `tests/unit/test_validation.py::test_global_question_routes_compile_with_step_specific_provider_visibility`, which checks inherited `GLOBAL` routes are compiled per-step and drive provider-visible route lists for provider-backed vs non-provider steps.
- Step-local suppression removes inherited routes before availability/provider visibility:
  covered by `tests/unit/test_validation.py::test_route_helper_defaults_and_global_suppression_compile_from_route_metadata`, which asserts `Route.disabled()` removes inherited `failed` from `available_routes`, provider-visible route lists, and `compiled.route(...)`.
- Legacy `ControlRoutes(question=...)` lowers through the compiled route model without reintroducing runtime injection:
  covered by `tests/unit/test_validation.py::test_core_control_routes_compile_provider_visibility_and_non_provider_defaults`, which checks compatibility-derived `question` behavior across prompt, python, and child-workflow steps.
- Preserved inspection/report behavior for inherited hidden `GLOBAL` routes:
  covered by `tests/runtime/test_runtime_static_graph.py::test_route_table_and_compile_report_include_hidden_global_routes`, which asserts the route table still shows the `GLOBAL` declaration and the compile report keeps declaration-based route and hidden-route counts.

## Preserved invariants checked
- `runtime_control_routes` remains a derived compatibility view only for legacy question defaults.
- Explicit `GLOBAL` routes remain separately inspectable while effective per-step compiled tables expose inherited route metadata.
- Static graph and compile-report outputs stay additive and deterministic after the compiled-route unification.

## Edge cases and failure paths
- Non-provider steps inheriting `GLOBAL` question routes remain runtime-legal but provider-invisible.
- Hidden inherited routes do not inflate compile-report summary counts when compiled step tables include inherited `GLOBAL` routes.
- Suppressed inherited routes remain present only as disabled compiled metadata and raise `RoutingError` when selected.

## Known gaps
- This phase intentionally does not test canonical `outcome.route_fields` parsing, provider schema generation, or runtime `Outcome.route_fields` projection because those belong to later phases.
- The focused route-model suite is deterministic and local; no timing, network, or ordering flake risks were introduced.
