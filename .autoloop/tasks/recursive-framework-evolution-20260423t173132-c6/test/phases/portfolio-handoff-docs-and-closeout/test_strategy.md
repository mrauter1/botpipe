# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c6
- Pair: test
- Phase ID: portfolio-handoff-docs-and-closeout
- Phase Directory Key: portfolio-handoff-docs-and-closeout
- Phase Title: Portfolio Handoff And Closeout
- Scope: phase-local producer artifact

## Coverage map

- AC-1 happy path: `tests/runtime/test_task_to_workflow_strategy.py::test_task_to_workflow_strategy_runs_and_publishes_concrete_adapt_handoff_without_widening_summary_fields`
  Stabilization: scripted provider turns, filesystem-only assertions, and explicit checks that neither `wf_candidate_workflow_to_adapted_execution_plan` nor the selected workflow run folder was created.
- AC-1 failure paths: `tests/runtime/test_task_to_workflow_strategy.py::test_task_to_workflow_strategy_publish_strategy_rejects_non_concrete_adapt_handoff`
  Covered cases: missing downstream building-block name in `workflow_strategy_package.md`, missing selected-workflow name in the existing summary `next_action`, and missing downstream building-block name in `strategy_next_action.md`.
- AC-2 preserved schema invariants:
  `tests/runtime/test_task_to_workflow_strategy.py::test_task_to_workflow_strategy_package_compiles_with_explicit_control_contracts` freezes the `package_strategy` schema binding to `StrategyPackagePayload` and the exact payload field set.
  `tests/runtime/test_task_to_workflow_strategy.py::test_task_to_workflow_strategy_runs_and_publishes_concrete_adapt_handoff_without_widening_summary_fields` freezes the published `strategy_summary.json` field set on the adapt route.
- AC-3 recursive closeout proof:
  `tests/test_architecture_baseline_docs.py::test_recursive_memory_cycle_six_closeout_proof_stays_explicit_without_claiming_recursive_wrapper_parity` freezes the cycle-6 memory wording, the `72 passed` proof count, and the no-recursive-wrapper-parity claim boundary.

## Preserved invariants checked

- `task_to_workflow_strategy` still stops at strategy publication.
- No new `StrategyPackagePayload` fields are introduced.
- No new `strategy_summary.json` fields are introduced.
- The adapt handoff stays on existing package and next-action artifacts instead of hidden execution.

## Known gaps

- No separate full-engine failure run is added for every malformed adapt artifact combination; the publish-step failure paths are covered deterministically at the callback level to avoid redundant scripted-provider duplication.
