# Test Author ↔ Test Auditor Feedback

- Task ID: below-is-the-revised-standalone-correction-spec-91e19feb
- Pair: test
- Phase ID: align-prompt-route-wording
- Phase Directory Key: align-prompt-route-wording
- Phase Title: Align Prompt Route Wording
- Scope: phase-local authoritative verifier artifact

- Added a self-contained regression in `tests/runtime/test_workflow_to_eval_suite.py` that seeds the workflow compile cache before monkeypatching `write_validated_eval_case_manifest`, then asserts `invoke_python_step(...)` recompiles fresh handlers and still raises `ValidationError` for missing `case_ids`.
- Expanded `test_strategy.md` with an explicit AC-to-test coverage map, preserved invariants, failure paths, flake risk, and stabilization notes for the helper cache-order seam.
