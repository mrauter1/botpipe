# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260423t173132-c8
- Pair: implement
- Phase ID: workflow-and-eval-to-refined-workflow-package
- Phase Directory Key: workflow-and-eval-to-refined-workflow-package
- Phase Title: Workflow And Eval To Refined Workflow Package
- Scope: phase-local authoritative verifier artifact

- `IMP-001` | `blocking` | `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py` (`on_capture_refinement_context`, `on_publish_refined_workflow`): the workflow copies `baseline_evaluation_summary.json` verbatim but never verifies that the supplied evaluation summary belongs to the selected workflow. A caller can pass `selected_workflow=release_candidate_to_go_no_go` and an evaluation summary for another workflow, and the package will still publish a candidate refinement receipt for `release_candidate_to_go_no_go` against mismatched evidence. Minimal fix: require an explicit selected-workflow identifier in the evaluation summary contract and reject runs where it does not match the validated selected workflow name; add a runtime rejection test that proves cross-workflow evidence drift is blocked before publication.
- `IMP-002` | `non-blocking` | Re-review result: `IMP-001` is addressed. The implementation now validates `baseline_evaluation_summary.json.selected_workflow_name` during capture and publication, the workflow doc declares the tighter input contract, and targeted proof includes the new rejection case. I found no additional actionable phase-scope findings in this pass.
