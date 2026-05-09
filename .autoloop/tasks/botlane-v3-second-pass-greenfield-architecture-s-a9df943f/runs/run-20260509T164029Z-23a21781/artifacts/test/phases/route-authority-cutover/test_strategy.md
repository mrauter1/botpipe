# Test Strategy

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: test
- Phase ID: route-authority-cutover
- Phase Directory Key: route-authority-cutover
- Phase Title: Make WorkflowPlan Sole Route Authority
- Scope: phase-local producer artifact

## Behavior-to-Test Coverage Map

- Canonical route authority:
  covered by existing route-contract, validation, and step-plan tests that derive available/provider-visible/runtime-control route views from `WorkflowPlan.routes` instead of step-owned route tables.
- Nested branch-group route authority:
  covered by `tests/runtime/test_runtime_static_graph.py::test_branch_group_payloads_are_additive_in_static_graph_and_topology`, which verifies nested branch and fan-in route payloads still resolve through canonical compiled route data.
- Preserved top-level export boundary:
  covered by the same static-graph regression test, which now asserts top-level transition exports and `route_table.md` remain filtered to top-level workflow steps even though internal branch steps live in `WorkflowPlan.routes`.
- Strictness regression guard:
  covered by `tests/strictness/test_no_internal_compat_layers.py::test_maintained_python_sources_do_not_reintroduce_step_owned_route_table_symbols`, which fails on `_route_table` / `_effective_route_table` symbol reintroduction across maintained sources.

## Preserved Invariants Checked

- Top-level available, authored, provider-visible, and runtime-control route views stay unchanged.
- Branch-group internal route visibility is still present in nested inspection payloads.
- Public top-level static-graph and route-table artifacts do not leak branch internal step rows.

## Edge Cases

- Branch-group fan-in routes remain visible in nested payloads while hidden from top-level transition tables.
- Canonical route ownership still works when internal branch routes and top-level step routes coexist in the same `WorkflowPlan.routes` mapping.

## Failure Paths

- Any reintroduction of step-owned `_route_table` / `_effective_route_table` symbols in maintained sources should fail strictness.
- Any regression that exposes internal branch steps in top-level static-graph transitions or route-table rows should fail the new static-graph regression assertions.

## Known Gaps

- This test pass did not add new capability-export-specific assertions; that surface is still covered indirectly through existing optimizer and CLI suites run in validation.
- Out-of-scope service-boundary, SDK one-step, and step-finalization behaviors remain untouched in this phase.

## Validation

- Focused:
  `.venv-test/bin/python -m pytest -q tests/runtime/test_runtime_static_graph.py`
- Full suite:
  `.venv-test/bin/python -m pytest -q`
- Result:
  `1279 passed, 1 warning`
