# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c8
- Pair: test
- Phase ID: workflow-and-eval-to-refined-workflow-package
- Phase Directory Key: workflow-and-eval-to-refined-workflow-package
- Phase Title: Workflow And Eval To Refined Workflow Package
- Scope: phase-local producer artifact

## Behavior-to-Test Coverage Map

- Discovery and contract surface:
- `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py` covers workflow discovery, alias exposure, compile-time step topology, and typed control contracts on the four pair steps.

- Happy path:
- The scripted runtime proof covers baseline snapshot capture, candidate workflow-surface publication, candidate manifest derivation, verification artifact publication, refinement receipt publication, and preservation of the authoritative selected workflow package.

- Failure paths:
- Missing baseline evidence artifact at publish time.
- Source evaluation-summary mismatch before pair-step execution.
- Baseline evaluation-summary drift after capture but before publish.
- Selected-workflow/authoring-surface mismatch.
- Candidate-manifest drift.
- Candidate files outside the selected workflow boundary.
- Selected-workflow state mismatch at publish time.

## Preserved Invariants Checked

- Runtime-injected control stays narrow: `expected_output_schema`, `available_routes`, and `route_contracts`.
- Candidate publication remains separate from the authoritative selected workflow package.
- Overlay validation still proves compile/test feasibility before publication.
- Recursive-memory baseline docs still record the shipped cycle 8 state expected by repo tests.

## Edge Cases / Stabilization

- The tests use `ScriptedLLMProvider`, temp repo copies, and workflow-module cache isolation for deterministic execution.
- Publish-side overlay validation is exercised without requiring network access or live provider backends.
- The regression coverage intentionally pins both evaluation-summary mismatch boundaries: initial input capture and post-capture artifact drift.

## Known Gaps

- Out-of-scope behaviors remain untested here: auto-running evaluation suites, sibling candidate workflow packages, and in-place promotion of the authoritative selected workflow package.
- This phase uses targeted proof, not the full repository test suite.
