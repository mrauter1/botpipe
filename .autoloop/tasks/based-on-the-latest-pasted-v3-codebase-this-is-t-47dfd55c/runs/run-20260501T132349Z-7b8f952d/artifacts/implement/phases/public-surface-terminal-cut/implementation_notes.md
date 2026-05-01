# Implementation Notes

- Task ID: based-on-the-latest-pasted-v3-codebase-this-is-t-47dfd55c
- Pair: implement
- Phase ID: public-surface-terminal-cut
- Phase Directory Key: public-surface-terminal-cut
- Phase Title: Public Surface And Terminal Cut
- Scope: phase-local producer artifact

## Files changed
- `autoloop/__init__.py`
- `autoloop/simple.py`
- `core/__init__.py`
- `core/primitives.py`
- `core/routes.py`
- `core/validation.py`
- `core/compiler.py`
- `core/engine.py`
- `core/history.py`
- `runtime/static_graph.py`
- `runtime/runner.py`
- `runtime/workspace.py`
- `runtime/cli.py`
- `autoloop_optimizer/company.py`
- `autoloop_optimizer/diagnostics.py`
- `autoloop_optimizer/optimization.py`
- `autoloop_optimizer/portfolio.py`
- `stdlib/__init__.py`
- `stdlib/control.py`
- `docs/authoring.md`
- `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
- `tests/runtime/test_optional_extensions.py`
- `workflows/workflow_package_to_composable_building_blocks/workflow.py`
- `tests/runtime/test_package_cli.py`
- `tests/runtime/test_security_finding_to_verified_remediation.py`
- `tests/runtime/test_workspace_and_context.py`
- `tests/runtime/test_workflow_integration_parity.py`
- `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- `tests/runtime/test_workflow_portfolio_to_operating_system.py`
- `tests/runtime/test_workflow_reference_resolution.py`
- `tests/runtime/test_workflow_run_history_to_failure_modes.py`
- `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_optimization_helpers.py`
- `tests/runtime/test_runtime_static_graph.py`
- `tests/strictness/test_no_compat.py`
- `tests/unit/test_stdlib_and_extensions.py`
- `tests/unit/test_validation.py`
- `workflows/task_to_workflow_strategy/workflow.py`
- `workflows/workflow_run_traces_to_optimization_candidates/params.py`

## Symbols touched
- Public terminals: `AWAIT_INPUT`, `FINISH`, `FAIL`, `SELF`
- Public runtime controls: `RequestInput`, `Goto`, `Fail`
- Public route helper: `Route.await_input(...)`
- Removed public simple keywords: `on_route` on `step`, `produce_verify_step`, `python_step`, `workflow_step`
- Stdlib helper rename: `await_input_on_outcome_tags`
- Public/runtime status string: `awaiting_input`
- Public run-record compatibility surface: `RunRecord.normalized_status`, `RunRecord.awaiting_input`
- Production status consumers: `task_to_workflow_strategy`, optimizer run-status filters, direct runtime snapshot helpers

## Checklist mapping
- Phase 1 / terminal cleanup: completed via terminal constant/export rename and static artifact terminal payload update.
- Phase 1 / runtime-control objects: completed for public dataclass surface and export wiring.
- Phase 1 / remove public `on_route`: completed for simple declarations/signatures and simple lowering.
- Phase 1 / remove old public names: covered for the phase-owned public surface, CLI payloads, direct consumer docs, and touched strict/public-surface/runtime tests; broader repo-wide removed-name sweeps remain outside this phase.

## Assumptions
- Internal core-step `on_route` hooks stay temporarily supported for later runtime-control work; only the public simple authoring surface is cut in this phase.
- Legacy persisted run metadata with status `paused` still needs to remain answerable during the rename.
- Direct consumer snapshot helpers should emit canonical `awaiting_input` even when they read legacy persisted `paused` run records.
- Compatibility fixtures may still seed raw persisted `paused` records, but direct runtime workflows and public test assertions should not.

## Preserved invariants
- Existing checkpoint payload shape stays unchanged in this phase (`pending_question` remains untouched).
- Route tag `"question"` remains the reserved provider/runtime route name.
- Engine semantics for pause-like suspension remain the same apart from terminal/status naming.
- Legacy persisted `run.json` files are not rewritten in place during read-path normalization.
- Child-workflow pause propagation remains event-driven; only the canonical status spelling changed.

## Intended behavior changes
- `PAUSE` is no longer exported from `autoloop` or `core`; `AWAIT_INPUT` is canonical.
- `RequestInput`, `Goto`, and `Fail` are importable from the public authoring surface.
- Simple authoring declarations reject `on_route` as a keyword.
- Public topology hook payloads no longer emit an `on_route` hook field.
- Runtime status normalization now emits `awaiting_input` for the await-input terminal.
- CLI payloads now expose `awaiting_input: bool` instead of the deprecated public `paused: bool`.
- Workspace, portfolio, company-operation, and diagnostics read APIs accept legacy `paused` filters but emit canonical `awaiting_input` status payloads.
- Direct public workflow/tests now use `AWAIT_INPUT` / `awaiting_input`, including child-workflow status branching and optimizer run-status defaults.

## Known non-changes
- Pending-input checkpoint/schema redesign is deferred to the runtime-control metadata phase.
- Internal core-step/runtime hook plumbing still uses `on_route`.
- Runtime selectors and compatibility helpers still use `latest_paused` / `RunRecord.paused` internally as read-path aliases during the cutover.
- Internal contract/compatibility fixtures outside this phase may still mention legacy `PAUSE` / `paused`.

## Expected side effects
- Consumers that imported `PAUSE` or passed `on_route=` through the simple surface now fail fast.
- CLI/help text now refers to awaiting-input runs, while record selection and snapshot filters still accept legacy paused records through compatibility logic.

## Validation performed
- `python3 -m py_compile` passed for all touched production files.
- `python3 -m py_compile` passed for touched test files.
- `pytest` execution was not possible: the environment has no `pytest` module.
- Import-time smoke execution was not possible with the system interpreter: the environment has no `pydantic` module.

## Deduplication / centralization
- Kept terminal-name normalization local to existing terminal/status helpers instead of adding new compatibility shims.
- Centralized public await-input helper renames through `core.primitives`, `core.routes`, and `stdlib.control` rather than leaving aliases behind.
