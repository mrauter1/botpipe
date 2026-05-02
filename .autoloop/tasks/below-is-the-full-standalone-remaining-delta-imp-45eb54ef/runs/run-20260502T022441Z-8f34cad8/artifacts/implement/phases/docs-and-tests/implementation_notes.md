# Implementation Notes

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: implement
- Phase ID: docs-and-tests
- Phase Directory Key: docs-and-tests
- Phase Title: Docs And Tests
- Scope: phase-local producer artifact

## Files changed
- `docs/authoring.md`
- `recursive_autoloop/run_recursive_autoloop_templates/workflow_authoring_doctrine.md.tmpl`
- `recursive_autoloop/run_recursive_autoloop_templates/framework_evolution_charter.md.tmpl`
- `recursive_autoloop/run_recursive_autoloop_templates/architecture_improvement_examples.md.tmpl`
- `tests/test_architecture_baseline_docs.py`
- `tests/runtime/test_history.py`
- `tests/runtime/test_runtime_tracing.py`
- `.../decisions.txt`

## Symbols touched
- Authoring-doc hook examples and return-contract snippets
- Authoring-doc runtime-control and worklist-helper examples
- Recursive template route-contract vocabulary
- Baseline-doc assertions for final hook/worklist vocabulary
- Synthetic history/trace hook-phase fixtures

## Checklist mapping
- Plan milestone 5, docs: document only `hook(ctx)`, final hook returns, direct controls, and worklist helpers.
- Plan milestone 5, tests: replace stale removed-surface expectations with fail-fast vocabulary checks and final `on_taken` trace/history expectations.
- Deferred: none within this phase.

## Assumptions
- Recursive authoring templates are active guidance surfaces for this phase, not archival docs.

## Preserved invariants
- No runtime/compiler behavior changed.
- Removed surfaces remain fail-fast; no compatibility wording was reintroduced.
- Route-local `on_taken` remains the only documented post-route hook surface.

## Intended behavior changes
- Active docs now show `python_step` and lifecycle hooks only in final `ctx`-only form.
- Active docs now teach `ctx.worklist(...)`, `ctx.worklists.<name>`, `ctx.current_worklist`, and helper-driven progression instead of route effects.
- Synthetic trace/history expectations now refer to `on_taken` rather than removed `on_route`.

## Known non-changes
- Workflow package docs that use ordinary English words like “outputs” were not mass-renamed when they were not describing removed API vocabulary.
- No additional runtime suites were edited beyond stale phase/vocabulary expectations.

## Expected side effects
- Doc-regression tests now fail if active docs or recursive templates reintroduce `route_required_outputs`, `(state, ctx)` python-step examples, or `Advance(...)` worklist guidance.

## Validation performed
- `./.venv/bin/pytest -q tests/test_architecture_baseline_docs.py tests/runtime/test_history.py tests/runtime/test_runtime_tracing.py`
- `./.venv/bin/pytest -q tests/contract/test_engine_contracts.py tests/unit/test_simple_surface.py tests/unit/test_validation.py tests/unit/test_primitives_and_stores.py tests/unit/test_optimization_helpers.py tests/runtime/test_runtime_static_graph.py tests/runtime/test_history.py tests/runtime/test_runtime_tracing.py`

## Deduplication / centralization
- Centralized removed-vocabulary checks for recursive templates in `tests/test_architecture_baseline_docs.py` instead of adding one-off assertions per template file.
