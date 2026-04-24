# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c5
- Pair: test
- Phase ID: task-to-candidate-workflow-set-package
- Phase Directory Key: task-to-candidate-workflow-set-package
- Phase Title: Task To Candidate Workflow Set Package
- Scope: phase-local producer artifact

## Behavior coverage map

- Discovery and compilation coverage:
  `tests/runtime/test_task_to_candidate_workflow_set.py`
  verifies package discovery, aliases, typed route contracts, and the explicit `publish_candidate_workflow_set` prerequisite tuple.
- Happy-path candidate-set publication:
  `tests/runtime/test_task_to_candidate_workflow_set.py`
  runs the workflow end-to-end with fake provider turns and checks the durable artifacts, machine-readable summary, receipt, builder baseline visibility, and `ready_for_strategy_selection=true`.
- Input guardrails and preserved invariants:
  `tests/runtime/test_task_to_candidate_workflow_set.py`
  checks blank `task_title` rejection and repeatable parameter normalization.
- Publication failure paths:
  `tests/runtime/test_task_to_candidate_workflow_set.py`
  rejects summaries that omit the builder baseline, claim `compose_needed` with only one recommended workflow, or set `ready_for_strategy_selection` to false.
- Adjacent regression surface:
  `tests/runtime/test_task_to_workflow_strategy.py`
  preserves the front-door composition path, the explicit adopted-child publish-step contract, strategy-only termination, and parent-local strategy artifact contracts.

## Flake control

- All coverage uses `tmp_path`, scripted fake providers, and direct artifact fixtures.
- No network, timing, random ordering, or external service dependencies are involved.

## Known gaps

- No end-to-end resume simulation currently deletes an adopted child artifact before `publish_strategy`; that runtime risk is covered indirectly by the preserved front-door compile contract test plus the generic engine missing-artifact contract tests.
