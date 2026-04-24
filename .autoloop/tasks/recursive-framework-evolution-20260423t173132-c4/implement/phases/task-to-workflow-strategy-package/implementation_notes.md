# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t173132-c4
- Pair: implement
- Phase ID: task-to-workflow-strategy-package
- Phase Directory Key: task-to-workflow-strategy-package
- Phase Title: Task To Workflow Strategy Package
- Scope: phase-local producer artifact

## Files changed

- `workflows/task_to_workflow_strategy/__init__.py`
- `workflows/task_to_workflow_strategy/workflow.toml`
- `workflows/task_to_workflow_strategy/params.py`
- `workflows/task_to_workflow_strategy/contracts.py`
- `workflows/task_to_workflow_strategy/workflow.py`
- `workflows/task_to_workflow_strategy/prompts/README.md`
- `workflows/task_to_workflow_strategy/prompts/frame_producer.md`
- `workflows/task_to_workflow_strategy/prompts/frame_verifier.md`
- `workflows/task_to_workflow_strategy/prompts/select_producer.md`
- `workflows/task_to_workflow_strategy/prompts/select_verifier.md`
- `workflows/task_to_workflow_strategy/prompts/package_producer.md`
- `workflows/task_to_workflow_strategy/prompts/package_verifier.md`
- `workflows/task_to_workflow_strategy/assets/strategy_package_checklist.md`
- `docs/workflows/task_to_workflow_strategy.md`
- `tests/runtime/test_task_to_workflow_strategy.py`
- `.autoloop/tasks/recursive-framework-evolution-20260423t173132-c4/decisions.txt`

## Symbols touched

- `workflows.task_to_workflow_strategy.TaskToWorkflowStrategy`
- `workflows.task_to_workflow_strategy.Parameters`
- `workflows.task_to_workflow_strategy.TaskFramingPayload`
- `workflows.task_to_workflow_strategy.StrategySelectionPayload`
- `workflows.task_to_workflow_strategy.StrategyPackagePayload`
- `tests.runtime.test_task_to_workflow_strategy._install_repo_task_to_workflow_strategy_package`

## Checklist mapping

- Phase 2 workflow package: implemented via `workflows/task_to_workflow_strategy/` with deterministic bootstrap, portfolio capture, task framing, strategy selection, strategy packaging, and terminal publication receipt.
- Phase 2 docs: implemented in `docs/workflows/task_to_workflow_strategy.md`.
- Phase 2 runtime proof: implemented in `tests/runtime/test_task_to_workflow_strategy.py`.
- Plan phase 3 recursive-memory closeout: intentionally not touched in this phase-local turn.

## Assumptions

- The repo-root package layout and the cycle-4 workflow-catalog seam remain authoritative over the retired `src/autoloop/...` paths in the request template.
- `workflow_idea_to_workflow_package` remains the standing builder baseline that must appear in front-door comparisons when present in the portfolio snapshot.

## Preserved invariants

- The front-door workflow stops at strategy publication and does not auto-run the selected downstream workflow.
- The runtime/provider boundary remains narrow: only `expected_output_schema`, `available_routes`, and `route_contracts` are runtime-injected control data.
- `workflow.toml` remains metadata-only; no new manifest fields were added.

## Intended behavior changes

- Autoloop now ships a discoverable `task_to_workflow_strategy` front-door workflow package that turns arbitrary tasks into a durable strategy package.
- The package publishes `workflow_portfolio_snapshot.json`, `workflow_strategy_package.md`, `strategy_summary.json`, `strategy_next_action.md`, and `strategy_receipt.json` as stable terminal artifacts.
- Terminal publication now validates that at least three candidates were compared and that the builder baseline stayed in the compared set.

## Known non-changes

- No downstream workflow execution, automatic routing, or child-run invocation was added.
- No recursive memory files under `.autoloop_recursive/` were updated in this phase-local turn.
- Existing domain workflows and reusable building blocks were not migrated or retuned here.

## Expected side effects

- Workflow discovery now includes `task_to_workflow_strategy`.
- Strategy-style tasks can be packaged into an explicit route decision without losing the compared-candidate rationale or next-action handoff.

## Validation performed

- `.venv/bin/python -m compileall workflows/task_to_workflow_strategy tests/runtime/test_task_to_workflow_strategy.py`
- `.venv/bin/pytest -q tests/runtime/test_task_to_workflow_strategy.py`
- `.venv/bin/pytest -q tests/runtime/test_task_to_workflow_strategy.py tests/runtime/test_compatibility_runtime.py`

## Deduplication / centralization decisions

- Reused the shared catalog seam through `write_workflow_portfolio_snapshot(...)` instead of adding ad hoc repo scraping to the new workflow package.
- Kept publish-time validation in the workflow-local `publish_strategy` system step rather than widening runtime routing or publication behavior.
