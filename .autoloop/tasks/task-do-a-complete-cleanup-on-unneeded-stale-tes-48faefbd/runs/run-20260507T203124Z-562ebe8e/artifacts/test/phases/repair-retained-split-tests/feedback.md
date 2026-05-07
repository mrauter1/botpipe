# Test Author ↔ Test Auditor Feedback

- Task ID: task-do-a-complete-cleanup-on-unneeded-stale-tes-48faefbd
- Pair: test
- Phase ID: repair-retained-split-tests
- Phase Directory Key: repair-retained-split-tests
- Phase Title: Repair retained split tests
- Scope: phase-local authoritative verifier artifact

- Added one regression guard in `tests/unit/stdlib/test_authoring_helpers.py` that AST-scans the retained shared test file for forbidden `autoloop.workflows.*.params` imports.
- Re-ran `.venv/bin/python -m pytest tests/strictness/test_no_compat.py tests/contract tests/unit -q` after the added guard; result: `786 passed, 1 warning`.

- `TST-001` `non-blocking`: `tests/unit/stdlib/test_authoring_helpers.py::test_retained_stdlib_authoring_test_stays_free_of_repo_owned_workflow_package_params` currently only rejects `ast.ImportFrom` nodes. A future `import autoloop.workflows.workflow_and_eval_to_refined_workflow_package.params as refinement_params` would reintroduce the forbidden dependency without tripping this guard. Minimal fix: extend the AST walk to also reject matching `ast.Import` aliases for the same forbidden modules.
