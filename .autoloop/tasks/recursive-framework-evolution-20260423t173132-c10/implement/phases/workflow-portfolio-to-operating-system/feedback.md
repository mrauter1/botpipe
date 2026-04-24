# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260423t173132-c10
- Pair: implement
- Phase ID: workflow-portfolio-to-operating-system
- Phase Directory Key: workflow-portfolio-to-operating-system
- Phase Title: Workflow Portfolio To Operating System
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` [workflows/workflow_portfolio_to_operating_system/workflow.py::_HIDDEN_EXECUTION_MARKERS, _contains_hidden_execution_signal(...), WorkflowPortfolioToOperatingSystem.on_publish_portfolio_operating_system] The publish gate does not fully enforce AC-3's "reject outputs that imply hidden downstream execution" rule. It only scans `workflow_portfolio_operating_system.md` and `portfolio_next_actions.md`, and its phrase allowlist is narrow enough that obvious forbidden variants like `The runtime queues workflow_and_eval_to_refined_workflow_package next.`, `This package automatically queues the refinement workflow.`, or `The system will launch ... after publication.` all pass. `portfolio_operating_summary.json["next_action"]` is not checked at all, so a hidden-execution implication can also survive there even when the markdown files are clean. Minimal fix: centralize one stronger hidden-execution validator for publication artifacts, apply it to the markdown artifacts and the summary `next_action`, and add proof cases that cover queue/launch/execute/automatic phrasing variants.
