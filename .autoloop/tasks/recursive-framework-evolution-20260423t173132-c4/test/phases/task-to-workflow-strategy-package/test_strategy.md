# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c4
- Pair: test
- Phase ID: task-to-workflow-strategy-package
- Phase Directory Key: task-to-workflow-strategy-package
- Phase Title: Task To Workflow Strategy Package
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Discovery surface:
  `tests/runtime/test_task_to_workflow_strategy.py::test_repo_workflows_namespace_discovers_task_to_workflow_strategy_package`
  covers registry discovery, package aliases, and manifest-path resolution for the new front-door workflow package.
- Compilation and control-contract surface:
  `tests/runtime/test_task_to_workflow_strategy.py::test_task_to_workflow_strategy_package_compiles_with_explicit_control_contracts`
  covers the compiled step order, terminal `publish_strategy` boundary, legal routes, required-artifact contracts, and the presence of narrow expected-output schemas.
- Documentation evidence surface:
  `tests/runtime/test_task_to_workflow_strategy.py::test_task_to_workflow_strategy_package_docs_capture_decision_records`
  covers the shipped decision records, route grammar, runtime-injected control contract, and explicit test evidence linkage in the workflow doc.
- Parameter validation and normalization:
  `tests/runtime/test_task_to_workflow_strategy.py::test_task_to_workflow_strategy_package_rejects_blank_task_title`
  and
  `tests/runtime/test_task_to_workflow_strategy.py::test_task_to_workflow_strategy_package_normalizes_repeatable_inputs`
  cover required task identity, whitespace trimming, duplicate removal, and empty-to-`None` normalization.
- End-to-end strategy publication happy path:
  `tests/runtime/test_task_to_workflow_strategy.py::test_task_to_workflow_strategy_package_runs_and_publishes_terminal_strategy_artifacts`
  covers deterministic portfolio capture, explicit candidate comparison, terminal strategy artifacts, publication receipt contents, and the invariant that no downstream workflow executes implicitly.
- Publish-boundary failure paths:
  `tests/runtime/test_task_to_workflow_strategy.py::test_task_to_workflow_strategy_publish_strategy_rejects_summary_without_builder_baseline`
  and
  `tests/runtime/test_task_to_workflow_strategy.py::test_task_to_workflow_strategy_publish_strategy_rejects_compose_summary_with_only_one_workflow`
  cover terminal rejection when the builder baseline is omitted from compared candidates and when a `compose` strategy fails to name at least two downstream workflows.

## Preserved invariants checked

- The front-door workflow remains a strategy-packaging workflow and does not auto-run the selected downstream workflow.
- The builder baseline stays explicit in the terminal summary rather than being implied by provider prose.
- Runtime-injected control remains narrow: tests lock route contracts and expected-output-schema presence instead of introducing broader runtime metadata.
- Terminal publication artifacts remain filesystem-first and inspectable: `workflow_strategy_package.md`, `strategy_summary.json`, `strategy_next_action.md`, and `strategy_receipt.json`.

## Edge cases and failure paths

- Blank `task_title` workflow parameter.
- Duplicate and whitespace-padded repeatable inputs.
- Missing builder baseline in `comparison_candidates`.
- Illegal `compose` package with only one recommended workflow.

## Flake risk and stabilization

- Coverage is filesystem-local and deterministic under `tmp_path`.
- The end-to-end workflow run uses `ScriptedLLMProvider` with fixed producer/verifier outcomes, so there is no external model, timing, or network dependency.
- Publish-boundary failure tests call `on_publish_strategy(...)` directly to isolate deterministic terminal validation instead of depending on a longer multi-step run.

## Known gaps

- There is no separate direct failure test yet for the `create_new` route requiring `workflow_idea_to_workflow_package` in `recommended_workflows`; the current suite already locks the builder-baseline invariant and the dominant `run_existing` / `compose` terminal behaviors for this phase.
