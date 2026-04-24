# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t173132-c5
- Pair: implement
- Phase ID: workflow-capability-snapshot-seam
- Phase Directory Key: workflow-capability-snapshot-seam
- Phase Title: Workflow Capability Snapshot Seam
- Scope: phase-local producer artifact

## Files changed

- `core/workflow_capabilities.py`
- `runtime/loader.py`
- `runtime/cli.py`
- `runtime/__init__.py`
- `stdlib/portfolio.py`
- `stdlib/__init__.py`
- `docs/architecture.md`
- `docs/authoring.md`
- `tests/runtime/test_compatibility_runtime.py`
- `tests/unit/test_stdlib_and_extensions.py`

## Symbols touched

- `core.workflow_capabilities.inspect_workflow_capabilities`
- `core.workflow_capabilities.load_workflow_package_contract`
- `core.workflow_capabilities.workflow_capability_payload`
- `core.workflow_capabilities.workflow_parameter_fields`
- `runtime.loader.inspect_workflow_capabilities`
- `runtime.loader._load_resolved_workflow`
- `runtime.cli._handle_workflows_show`
- `stdlib.portfolio.write_workflow_capability_snapshot`
- `stdlib.portfolio.write_workflow_portfolio_snapshot`

## Checklist mapping

- AC-1: added the separate importing capability-inspection seam in `core/workflow_capabilities.py`, runtime re-exports in `runtime/loader.py` and `runtime/__init__.py`, and compatibility coverage in `tests/runtime/test_compatibility_runtime.py`.
- AC-2: added `write_workflow_capability_snapshot(...)` in `stdlib/portfolio.py`, exported it from `stdlib/__init__.py`, and covered the workflow-local artifact boundary in `tests/unit/test_stdlib_and_extensions.py`.
- AC-3: documented the narrow-vs-rich boundary in `docs/architecture.md` and `docs/authoring.md`, and revalidated the existing front-door workflow via `tests/runtime/test_task_to_workflow_strategy.py`.

## Assumptions

- The active phase contract is narrower than the full cycle request, so this turn only ships the capability-inspection/helper seam and not the later candidate-set workflow.
- The repo-root equivalents recorded in planning remain authoritative for this cycle; the stale `src/autoloop/...` paths were not resurrected.

## Preserved invariants

- `discover_workflow_catalog(...)` remains metadata-only and non-importing.
- `workflow.toml` remains metadata-only; no new manifest fields were added.
- `write_workflow_portfolio_snapshot(...)` keeps its existing lightweight payload shape.
- Runtime/provider control metadata remains limited to `expected_output_schema`, `available_routes`, and `route_contracts`.
- `autoloop workflows show <workflow>` keeps its existing CLI shape.

## Intended behavior changes

- Added a reusable importing inspection seam for normalized workflow parameters and compiled step contracts.
- Added `write_workflow_capability_snapshot(...)` for workflow-local rich portfolio inspection artifacts.
- Runtime now exposes `inspect_workflow_capabilities(...)` alongside the existing lightweight catalog discovery surface.

## Known non-changes

- No new workflow package or workflow invocation path was added in this phase.
- `task_to_workflow_strategy` logic and artifact contract were left unchanged.
- Recursive memory files under `.autoloop_recursive/` were not updated in this phase-local implement slice.

## Expected side effects

- Capability inspection now imports and compiles workflow packages when explicitly requested.
- Portfolio workflows can opt into a richer `workflow_capability_snapshot.json` artifact without affecting lightweight discovery consumers.

## Validation performed

- `.venv/bin/python -m py_compile core/workflow_capabilities.py runtime/loader.py runtime/cli.py runtime/__init__.py stdlib/portfolio.py stdlib/__init__.py tests/runtime/test_compatibility_runtime.py tests/unit/test_stdlib_and_extensions.py`
- `.venv/bin/pytest -q tests/runtime/test_compatibility_runtime.py tests/unit/test_stdlib_and_extensions.py tests/runtime/test_task_to_workflow_strategy.py tests/test_architecture_baseline_docs.py`

## Deduplication / centralization decisions

- Centralized importing workflow-package validation and parameter-field normalization in `core/workflow_capabilities.py` so runtime resolution and capability inspection share one loader path.
- Kept the new snapshot helper in `stdlib/portfolio.py` beside the existing lightweight portfolio snapshot helper to make the additive boundary obvious.
