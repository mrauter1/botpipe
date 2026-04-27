# Test Strategy

- Task ID: recursive-framework-evolution-20260427t121046-bootstrap
- Pair: test
- Phase ID: prompts-docs-and-report
- Phase Directory Key: prompts-docs-and-report
- Phase Title: Prompts Docs And Report
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- Prompt README ownership, failure-seed, optimization-depth, and candidate-budget guidance:
  Covered by `tests/test_architecture_baseline_docs.py::test_optimizer_prompt_readme_freezes_seed_ownership_depth_and_budget_guidance`.
- Producer prompt instructions to read `workflow_optimization_scope.json`, apply `optimization_depth`, and treat `max_candidates_per_pass` as a soft budget:
  Covered by `tests/test_architecture_baseline_docs.py::test_optimizer_step_prompts_freeze_scope_and_over_budget_guidance`.
- Verifier prompt instructions to avoid rejecting solely on over-budget candidate count and to reject hidden execution or ownership violations:
  Covered by `tests/test_architecture_baseline_docs.py::test_optimizer_step_prompts_freeze_scope_and_over_budget_guidance`.
- Workflow doc and `report.md` statements for deterministic seed ownership, validation-only publication, and no-rerun/no-ablation semantics:
  Covered by `tests/test_architecture_baseline_docs.py::test_optimizer_workflow_doc_and_report_freeze_publication_boundaries`.

## Preserved Invariants Checked

- Prompt-only semantics remain explicit for `optimization_depth` and `max_candidates_per_pass`.
- Failure-scenario seed ownership stays separate from the final producer-authored failure artifact.
- Docs and report continue to state that the optimizer is candidate-only and does not execute reruns, ablations, or source mutation.

## Edge Cases And Failure Paths

- Report coverage asserts both the semantic summary and the preserved-boundaries list so regressions in either section fail fast.
- Step-prompt coverage checks both producer and verifier surfaces, which catches asymmetric drift where only one side of the pair is updated.

## Flake Risks / Stabilization

- No timing, network, or ordering risks. Coverage is deterministic string-level contract validation over repository files.

## Validation Run

- `.venv/bin/python -m pytest tests/test_architecture_baseline_docs.py -k "optimizer_prompt_readme_freezes_seed_ownership_depth_and_budget_guidance or optimizer_step_prompts_freeze_scope_and_over_budget_guidance or optimizer_workflow_doc_and_report_freeze_publication_boundaries"` -> passed
- `.venv/bin/python -m pytest tests/test_architecture_baseline_docs.py` -> failed only on the two pre-existing recursive-memory charter assertions outside this phase scope

## Known Gaps

- This phase adds documentation-contract regression coverage only; runtime behavior coverage remains owned by the earlier workflow-semantics-and-contracts phase tests.
