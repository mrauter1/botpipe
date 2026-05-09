# Implementation Notes

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: implement
- Phase ID: single-step-parity-and-cleanup
- Phase Directory Key: single-step-parity-and-cleanup
- Phase Title: Single Step Parity And Cleanup
- Scope: phase-local producer artifact

## Files changed

- `botlane/core/step_plans.py`
- `botlane/sdk.py`
- `botlane/core/workflow_capabilities.py`
- `botlane/runtime/loader.py`
- `tests/contract/test_single_step_plan_equivalence.py`
- `tests/strictness/test_no_compat.py`
- `decisions.txt`

## Symbols touched

- `botlane.core.step_plans.SingleStepPlan`
- `botlane.sdk._build_single_step_plan`
- `botlane.core.workflow_capabilities._resolved_from_workflow_class`
- `botlane.core.workflow_capabilities._load_isolated_workflow_module`
- `botlane.core.workflow_capabilities._import_discovered_module`
- `botlane.core.workflow_capabilities._no_bytecode_writes`
- `botlane.runtime.loader._cleanup_workflow_pycache`

## Checklist mapping

- Plan milestone 10 / phase AC-1: added `SingleStepPlan` as an internal adapter only; `Botlane.step(...)` remains on the synthetic workflow path.
- Plan milestone 10 / deliverable: added `tests/contract/test_single_step_plan_equivalence.py` covering supported step declarations, policy layering, route parity, typed input/params, and direct synthetic-run equivalence.
- Phase cleanup / full-suite green: fixed capability-inspection `parameters_model` resolution for workspace package workflows and removed workspace workflow `__pycache__` dirtiness during runtime/capability imports.

## Assumptions

- Exact execution-path replacement for `Botlane.step(...)` was not required once internal plan parity was proven and the synthetic path remained source-compatible.
- Full-suite blockers discovered during validation were in scope to fix because this phase requires a fully green `pytest` run.

## Preserved invariants

- `Botlane.step(...)` signature and behavior remain unchanged.
- `StepResult.value` remains `None`.
- Single-step support matrix was not broadened.
- `SingleStepPlan` remains internal-only and is not exported from package `__init__` files.
- Public route sentinels and simple/SDK authoring behavior remain unchanged.

## Intended behavior changes

- `SingleStepPlan` now exists as an internal parity target and can be derived from the current synthetic workflow path.
- Workflow capability inspection now reports `parameters_model` for workspace manifest packages that expose `Params` via `params.py` or package exports.
- Runtime/capability imports no longer leave workspace workflow `__pycache__` entries behind, avoiding false git-dirty failures before runtime git tracking starts.

## Known non-changes

- `Botlane.step(...)` does not execute through `SingleStepPlan`.
- No temporary execution-service or engine bridges were removed in this phase.
- No public exports or root API ordering changed.

## Expected side effects

- Capability/CLI metadata for workspace package workflows is richer and matches runtime parameter resolution.
- Workspace git-tracking runs no longer fail solely because workflow inspection/import created `__pycache__` directories.

## Validation performed

- `.venv/bin/python -m pytest tests/contract/test_single_step_plan_equivalence.py`
- `.venv/bin/python -m pytest tests/unit/test_sdk_facade.py`
- `.venv/bin/python -m pytest tests/runtime/test_package_cli.py::test_cli_serializes_typed_workflow_parameters_as_json_safe_values -q`
- `.venv/bin/python -m pytest tests/runtime/test_package_cli.py::test_cli_mutating_commands_route_runtime_git_and_trace_overrides_through_typed_config -q`
- `.venv/bin/python -m pytest tests/unit/optimizer/test_portfolio_helpers.py::test_portfolio_helpers_keep_catalog_snapshot_lightweight_and_capability_snapshot_rich -q`
- `.venv/bin/python -m pytest tests/strictness/test_no_compat.py -q`
- `.venv/bin/python -m pytest`

## Deduplication / centralization

- Reused the existing synthetic workflow builder as the single source for `SingleStepPlan` derivation instead of adding a parallel single-step compilation path.
- Centralized capability-import bytecode suppression in `botlane/core/workflow_capabilities.py` rather than adding one-off cleanup at CLI call sites.
