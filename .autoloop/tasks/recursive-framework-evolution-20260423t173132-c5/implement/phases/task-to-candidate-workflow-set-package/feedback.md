# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260423t173132-c5
- Pair: implement
- Phase ID: task-to-candidate-workflow-set-package
- Phase Directory Key: task-to-candidate-workflow-set-package
- Phase Title: Task To Candidate Workflow Set Package
- Scope: phase-local authoritative verifier artifact

- IMP-001 [blocking] `task_to_workflow_strategy`'s `publish_strategy` step no longer has an explicit artifact contract that matches its real runtime inputs. Evidence: [workflows/task_to_workflow_strategy/workflow.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/workflows/task_to_workflow_strategy/workflow.py:187) declares `publish_strategy.requires` with only the parent portfolio, analysis, and strategy artifacts, but [on_publish_strategy](/home/rauter/autoloop_v3_bkp/autoloop_v3/workflows/task_to_workflow_strategy/workflow.py:358) also reads the adopted child artifacts `candidate_route_posture.md`, `candidate_workflow_set.md`, `candidate_workflow_set_summary.json`, and `candidate_next_action.md`. The engine enforces `step.requires` before invoking a step ([core/engine.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/engine.py:501)), so a resumed or partially cleaned run can reach `publish_strategy` with a compiled/capability contract that says the step is runnable while the handler still dies late with `FileNotFoundError` once it touches the missing adopted child artifacts. The same incomplete contract is published in the workflow doc row at [docs/workflows/task_to_workflow_strategy.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/docs/workflows/task_to_workflow_strategy.md:182), which violates the explicit artifact-contract doctrine and undermines the new inspectability seam. Minimal fix: add the four adopted child artifacts to `publish_strategy.requires`, align the doc's `publish_strategy` artifact-contract row, and extend `tests/runtime/test_task_to_workflow_strategy.py` to lock the full publish-step prerequisite set at compile time.

Re-review result: `IMP-001` is resolved by the added `publish_strategy.requires` entries, the aligned `publish_strategy` artifact-contract doc row, and the compile-time assertion in `tests/runtime/test_task_to_workflow_strategy.py`. No blocking or non-blocking review findings remain in this verifier pass.
