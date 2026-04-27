# Test Author ↔ Test Auditor Feedback

- Task ID: recursive-framework-evolution-20260427t121046-bootstrap
- Pair: test
- Phase ID: workflow-semantics-and-contracts
- Phase Directory Key: workflow-semantics-and-contracts
- Phase Title: Workflow Semantics And Contracts
- Scope: phase-local authoritative verifier artifact

- Added a parametrized runtime regression test that proves the token, adversarial, and workflow-level skip gates preserve any pre-existing provider-authored artifact and only synthesize empty placeholders when the artifact is absent.
- Recorded an explicit AC-to-test coverage map, preserved invariants, failure paths, stabilization notes, and known prompt-text gaps in `test_strategy.md`.
- TST-001 | blocking | `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py` still does not exercise the provider-emitted `*_not_applicable` handler branch in `_finalize_candidate_artifact` (`producer_pass_not_applicable`, `verifier_rubric_pass_not_applicable`, and pair-step `token_pass_not_applicable` / `adversarial_generation_skipped` / `workflow_level_pass_not_applicable`). The new parametrized test covers only the deterministic skip gates (`on_route_*`). A regression that rewrites an existing provider-authored artifact to the minimal empty payload when a pair step itself returns a not-applicable outcome would still pass, despite the explicit requirement that valid provider-authored artifacts remain in place on not-applicable routes. Add a handler-level or scripted full-workflow test that seeds an existing artifact, returns a `*_not_applicable` outcome from the pair step, and asserts the artifact is preserved verbatim.
