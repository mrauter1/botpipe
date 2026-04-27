# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260426t220607-bootstrap
- Pair: implement
- Phase ID: verification-and-full-regression
- Phase Directory Key: verification-and-full-regression
- Phase Title: Verification And Full Regression
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking` — [tests/runtime/test_workflow_run_traces_to_optimization_candidates.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_workflow_run_traces_to_optimization_candidates.py:235): the phase contract explicitly called for runtime coverage of the enabled candidate-generation passes, but this file only exercises the skip gates for `optimize_tokens`, `adversarial_cases`, and `workflow_level`, plus publish-time validation. There is no runtime test that drives successful `optimize_producer`, `optimize_verifier_rubric`, enabled `optimize_tokens`, or enabled `adversarial_cases` outputs through the workflow and asserts the corresponding candidate artifacts were written. That leaves regressions in prompt wiring, route contracts, artifact paths, or artifact schemas in those passes unproved despite the implementation notes claiming the requested suite exists and passes. Minimal fix: add the missing runtime tests using the fake provider to exercise each enabled pass and assert the published candidate artifacts and routes.

- IMP-002 `blocking` — [tests/runtime/test_workflow_run_traces_to_optimization_candidates.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_workflow_run_traces_to_optimization_candidates.py:675): the request required `test_workflow_never_mutates_selected_workflow_source`, but the current coverage only proves that publication fails after an external mutation is injected. That is not the same safety proof as a successful end-to-end optimizer run leaving the selected workflow package unchanged. A regression that accidentally rewrites prompt or workflow files and then restores manifest parity before package-time validation, or mutates untouched files outside the manifest snapshot, would not be caught by the current test set. Minimal fix: add a success-path runtime test that snapshots the selected workflow package before a normal optimizer run and asserts the source tree is byte-for-byte unchanged afterward.

- IMP-003 `non-blocking` — [workflows/workflow_run_traces_to_optimization_candidates/contracts.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/workflows/workflow_run_traces_to_optimization_candidates/contracts.py:61): importing the optimizer contracts emits repeated Pydantic warnings because each model declares a `schema` field that shadows a `BaseModel` attribute. The implementation notes recorded this, and it does not currently fail tests, but it adds avoidable noise to every verification run and will make future `-W error` or stricter CI settings harder to adopt. Minimal fix: rename the field internally with an alias or move to a warning-free schema-literal pattern consistent with the repository’s contract helpers.
