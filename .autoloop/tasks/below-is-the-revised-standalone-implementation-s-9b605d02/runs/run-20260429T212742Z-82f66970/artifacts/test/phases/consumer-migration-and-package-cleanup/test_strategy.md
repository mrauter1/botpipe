# Test Strategy

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: test
- Phase ID: consumer-migration-and-package-cleanup
- Phase Directory Key: consumer-migration-and-package-cleanup
- Phase Title: Consumer Migration
- Scope: phase-local producer artifact

## Behavior Coverage Map

- Active consumer runtime fixtures stay on canonical naming only
  - Coverage: `tests/unit/test_stdlib_and_extensions.py::test_active_consumer_runtime_fixtures_avoid_legacy_authoring_tokens`
  - Files pinned: `test_optional_extensions.py`, `test_workspace_and_context.py`, `test_runtime_static_graph.py`, `test_workflow_package_to_composable_building_blocks.py`, `test_runtime_git_tracking.py`, `test_company_operation_to_recursive_improvement_cycle.py`, `test_workflow_run_history_to_failure_modes.py`
  - Regression caught: reintroduction of `SUCCESS`, `SystemStep`, `LLMStep`, `PairStep`, `RouteInfo`, `required_outputs`, `route_infos`, `route_required_outputs`, `transitions`, or `global_transitions`

- Canonicalized runtime workflow-package fixtures still execute correctly
  - Coverage: `tests/runtime/test_optional_extensions.py`, `tests/runtime/test_workspace_and_context.py`, `tests/runtime/test_runtime_static_graph.py`
  - Preserved invariants: run/resume behavior, git-tracking observability, child-workflow metadata shape, static-graph/topology artifact generation
  - Edge/failure paths: paused/resumed runs, fatal child workflow, typed child output validation failure, runtime tracing failure mode

## Validation Performed

- `./.venv/bin/python -m pytest tests/unit/test_stdlib_and_extensions.py -k 'active_consumer_runtime_fixtures_avoid_legacy_authoring_tokens or stdlib_modules_remain_pure_authoring_helpers' -q`
  - `2 passed, 94 deselected`
- `./.venv/bin/python -m pytest tests/runtime/test_optional_extensions.py tests/runtime/test_workspace_and_context.py tests/runtime/test_runtime_static_graph.py -q`
  - `35 passed`

## Flake Risk / Stabilization

- Static contract coverage reads committed repo files only; no timing or environment dependency.
- Runtime validation remains deterministic through `ScriptedLLMProvider`, tmp-path isolation, and no network dependency.

## Known Gaps

- Compatibility/provider/internal validation suites that intentionally retain legacy terms remain outside this phase’s test guard.
- The new static contract test intentionally scopes to the reviewer-listed active consumer runtime files rather than all repo files, so explicit migration/compat coverage can continue to exist without false failures.
