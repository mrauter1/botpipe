# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c7
- Pair: test
- Phase ID: cycle-seven-closeout
- Phase Directory Key: cycle-seven-closeout
- Phase Title: Cycle Seven Closeout
- Scope: phase-local producer artifact

## Coverage Map

- Behavior: cycle-7 closeout keeps the recorded roadmap proof aligned with the targeted helper/workflow/baseline-doc suite.
  Coverage: `tests/test_architecture_baseline_docs.py::test_recursive_memory_cycle_seven_closeout_proof_stays_explicit_without_claiming_recursive_wrapper_parity`
- Behavior: `workflow_to_eval_suite` verifier prompts keep artifact writes local to verification and do not leak publish-step outputs into verifier scope.
  Coverage: `tests/runtime/test_workflow_to_eval_suite.py::test_workflow_to_eval_suite_prompts_keep_step_local_contracts_explicit`
- Behavior: the targeted closeout suite still exercises the helper seam, the eval-suite workflow package, and the recursive-memory baseline together.
  Coverage: `.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py tests/runtime/test_workflow_to_eval_suite.py tests/test_architecture_baseline_docs.py`

## Preserved Invariants Checked

- Runtime/provider control surfaces remain limited to `expected_output_schema`, `available_routes`, and `route_contracts`.
- Cycle-7 closeout still stops short of runtime-owned evaluation execution or recursive wrapper cleanup.
- The documented closeout proof count stays at `77 passed` after test refinement.

## Edge Cases And Failure Paths

- Missing verifier `Write these artifacts` or `Evidence requirements` sections fail the workflow runtime prompt-contract test.
- Missing explicit non-write verifier guidance or leaked publish-artifact creation text fails the same prompt-contract test.
- A stale cycle-7 roadmap proof count fails the recursive-memory baseline-doc test.

## Known Gaps

- The roadmap proof-count assertion is intentionally exact; any future addition or removal inside the targeted closeout suite must update the recorded result deliberately.
- The closeout suite validates prompt contracts and baseline memory, not downstream evaluation execution, which remains intentionally out of scope.
