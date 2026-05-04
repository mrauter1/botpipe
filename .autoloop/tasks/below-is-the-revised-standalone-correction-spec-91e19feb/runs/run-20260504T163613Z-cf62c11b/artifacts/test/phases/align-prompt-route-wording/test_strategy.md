# Test Strategy

- Task ID: below-is-the-revised-standalone-correction-spec-91e19feb
- Pair: test
- Phase ID: align-prompt-route-wording
- Phase Directory Key: align-prompt-route-wording
- Phase Title: Align Prompt Route Wording
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- AC-1 retired wording removal in prompt bodies:
  `tests/test_architecture_baseline_docs.py::test_workflow_prompt_bodies_use_question_only_runtime_control_wording` scans non-README prompt bodies and fails on `Reserved routes` / retired reserved-set phrasing.
- AC-2 positive route-model wording in route-guidance prompt bodies:
  `tests/test_architecture_baseline_docs.py::test_workflow_prompt_bodies_use_question_only_runtime_control_wording` requires the positive `question`-only runtime-control marker and the authored-`blocked` / authored-`failed` ordinary-application-route marker.
- AC-3 shipped runtime prompt-package wording and route-model expectations:
  `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
  `tests/runtime/test_workflow_portfolio_to_operating_system.py`
  `tests/runtime/test_workflow_run_history_to_failure_modes.py`
  `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
  `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
  `tests/runtime/test_workflow_to_eval_suite.py`
  assert the shipped `question`-only default control contract, unscoped artifact names, and prompt README / prompt-body markers.
- Helper-based full-file regression for publish-step validation after monkeypatch:
  `tests/runtime/test_workflow_to_eval_suite.py::test_invoke_python_step_recompiles_after_workflow_module_monkeypatch` seeds the compile cache before monkeypatching the workflow module and verifies helper-driven invocation recompiles fresh handlers.

## Preserved Invariants Checked

- No test encodes `blocked` or `failed` as framework-default routes.
- Runtime package suites still compile and run with the shipped route topology and artifact naming.
- Test-only compile-cache isolation remains confined to helper-driven runtime invocations; production runtime behavior is not asserted to change.

## Edge Cases

- Route-guidance prompts are discovered structurally from prompt-body headings rather than a brittle hard-coded file list.
- The eval-suite publish path rejects a validated manifest that is missing the typed `case_ids` field even after a prior compile populated the workflow compiler cache.

## Failure Paths

- Prompt-body baseline fails if retired reserved-route wording reappears.
- Prompt-body baseline fails if the positive route-model markers disappear from updated route-guidance prompts.
- Eval-suite publish tests fail if helper-driven step invocation reuses a stale compiled handler after workflow-module monkeypatching.

## Validation

- `/tmp/autoloop-prompt-route-verify-sF91JR/bin/python -m pytest tests/test_architecture_baseline_docs.py::test_workflow_prompt_bodies_use_question_only_runtime_control_wording -q`
- `/tmp/autoloop-prompt-route-verify-sF91JR/bin/python -m pytest tests/runtime/test_workflow_to_eval_suite.py -q`
- `/tmp/autoloop-prompt-route-verify-sF91JR/bin/python -m pytest tests/runtime/test_company_operation_to_recursive_improvement_cycle.py tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/runtime/test_workflow_to_eval_suite.py tests/runtime/test_release_candidate_to_go_no_go.py -q`

## Flake Risks And Stabilization

- Risk: helper-based runtime tests can become order-dependent when workflow module handlers are monkeypatched after a prior compile.
- Stabilization: the new self-contained regression test seeds the cache explicitly and asserts recompilation through `invoke_python_step`, so the failure mode is deterministic instead of depending on full-file ordering.

## Known Gaps

- The shared baseline enforces stable marker fragments rather than full prompt prose snapshots; this is intentional to avoid brittle wording-only churn.
