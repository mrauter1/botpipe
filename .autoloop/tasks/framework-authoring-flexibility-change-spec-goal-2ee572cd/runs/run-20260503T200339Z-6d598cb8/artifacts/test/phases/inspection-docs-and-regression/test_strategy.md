# Test Strategy

- Task ID: `framework-authoring-flexibility-change-spec-goal-2ee572cd`
- Pair: `test`
- Phase ID: `inspection-docs-and-regression`
- Phase Directory Key: `inspection-docs-and-regression`
- Phase Title: `Inspection, Docs, And Regression Sweep`
- Scope: phase-local producer artifact

## Behavior-to-coverage map

- Inspection/static-graph JSON route views:
  Covered by `tests/runtime/test_runtime_static_graph.py`
  Checks authored routes, runtime-control routes, provider-visible interactive/full-auto routes, and route metadata on the static-step-graph and topology payloads.
- Text inspection artifacts:
  Covered by `tests/runtime/test_runtime_static_graph.py`
  Checks `route_table.md`, `topology.mmd`, and `compile_report.md` for authored vs runtime-control labeling, hidden/global routes, and interactive-only `question` visibility.
- CLI/capability read models:
  Covered by `tests/runtime/test_package_cli.py` and `tests/unit/test_stdlib_and_extensions.py`
  Checks `workflows show` output and selected-workflow decomposition/capability snapshots against the new route-view schema.
- Documentation contract:
  Covered by `tests/test_architecture_baseline_docs.py`
  Checks route-policy wording, static-vs-runtime validation wording, lazy worklist/runtime wording, typed-effects anchors, and explicit managed-artifact-role documentation anchors.

## Preserved invariants checked

- `CompiledStep.available_routes` remains the full execution-legal route set while the new authored/runtime-control/provider-visible views stay additive.
- Static graph still writes all canonical artifact files.
- Required-write reporting still distinguishes explicit vs inherited behavior.
- Hidden authored routes and hidden global routes remain represented without reviving default injected `blocked`/`failed`.

## Edge cases covered

- Interactive-only `question` route in text and JSON inspection surfaces.
- Hidden authored route rendered in both route table and Mermaid output.
- Hidden global route rendered without flattening into a generic visible route.
- Explicit empty `required_writes` vs inherited required writes.

## Failure paths / regressions targeted

- Drift between JSON inspection payloads and text inspection artifacts.
- Drift between docs wording and shipped managed-artifact behavior.
- Regression to legacy flat provider-visible route reporting in route tables or compile reports.

## Flake risks / stabilization

- No network or timing dependencies.
- Assertions use deterministic substring anchors and fixed in-memory workflows instead of environment-sensitive snapshots.

## Known gaps

- No full-document snapshotting for docs; coverage intentionally stays on required anchors to avoid brittle prose churn.
