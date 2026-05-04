# Implementation Notes

- Task ID: below-is-the-revised-standalone-correction-spec-91e19feb
- Pair: implement
- Phase ID: align-prompt-route-wording
- Phase Directory Key: align-prompt-route-wording
- Phase Title: Align Prompt Route Wording
- Scope: phase-local producer artifact

## Files Changed
- `workflows/*/prompts/*.md` non-README prompt bodies with `## Routes` or `## Route Guidance` sections
- `tests/test_architecture_baseline_docs.py`
- `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
- `tests/runtime/workflow_contract_helpers.py`
- `tests/runtime/test_release_candidate_to_go_no_go.py`
- `tests/runtime/test_workflow_portfolio_to_operating_system.py`
- `tests/runtime/test_workflow_run_history_to_failure_modes.py`
- `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
- `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- `tests/runtime/test_workflow_to_eval_suite.py`

## Symbols Touched
- `test_workflow_prompt_bodies_use_question_only_runtime_control_wording`
- `invoke_python_step`
- `invoke_after_verifier_hook`
- Prompt-package `required_markers` parametrizations in the six runtime suites above

## Checklist Mapping
- Plan item 1: complete; replaced retired reserved-route wording and added positive route-model markers in prompt bodies
- Plan item 2: complete; updated runtime prompt-package assertions to the new wording
- Plan item 3: complete; added shared baseline coverage that scans prompt bodies directly

## Assumptions
- Route-guidance prompt bodies are the non-README prompt markdown files containing `## Routes` or `## Route Guidance`.

## Preserved Invariants
- No runtime engine, workflow topology, or route-resolution behavior changed.
- Workflow compile-cache behavior in production code remains unchanged; cache isolation was applied only in test helpers.
- Workflow-specific route names, artifact contracts, and local escalation criteria stayed intact aside from the route-model framing rewrite.

## Intended Behavior Changes
- Prompt bodies now describe `question` as the only default runtime control route.
- Prompt bodies now describe authored `blocked` and `failed` as ordinary application routes rather than framework defaults.
- Shared baseline coverage now scans prompt bodies directly for both forbidden retired wording and required positive markers.

## Known Non-Changes
- Did not alter runtime compile/execute semantics in repository source; only stale test expectations and test-helper cache isolation changed.
- Did not rewrite prompt `README.md` files or workflow package docs beyond relying on their existing shipped vocabulary.

## Expected Side Effects
- Route-guidance prompt bodies now share a consistent preamble, including prompt families that previously had no explicit control-route wording.
- Helper-driven runtime step tests now recompile workflows after monkeypatches so module-level handler overrides are observed consistently within full-file pytest runs.

## Validation Performed
- `rg -n "Reserved routes|Use reserved routes only" workflows/*/prompts/*.md` returned no prompt-body matches.
- `.venv-autoloop-tests/bin/python -m pytest tests/test_architecture_baseline_docs.py::test_workflow_prompt_bodies_use_question_only_runtime_control_wording tests/runtime/test_company_operation_to_recursive_improvement_cycle.py::test_company_operation_to_recursive_improvement_cycle_prompt_readme_uses_shared_contract_sections tests/runtime/test_company_operation_to_recursive_improvement_cycle.py::test_company_operation_to_recursive_improvement_cycle_prompts_keep_step_local_contracts_explicit tests/runtime/test_workflow_portfolio_to_operating_system.py::test_workflow_portfolio_to_operating_system_prompt_readme_uses_shared_contract_sections tests/runtime/test_workflow_portfolio_to_operating_system.py::test_workflow_portfolio_to_operating_system_prompts_keep_step_local_contracts_explicit tests/runtime/test_workflow_run_history_to_failure_modes.py::test_workflow_run_history_to_failure_modes_prompt_readme_uses_shared_contract_sections tests/runtime/test_workflow_run_history_to_failure_modes.py::test_workflow_run_history_to_failure_modes_prompts_keep_step_local_contracts_explicit tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py::test_workflow_and_eval_to_refined_workflow_package_prompt_readme_uses_shared_contract_sections tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py::test_workflow_and_eval_to_refined_workflow_package_prompts_keep_step_local_contracts_explicit tests/runtime/test_workflow_package_to_composable_building_blocks.py::test_workflow_package_to_composable_building_blocks_prompt_readme_uses_shared_contract_sections tests/runtime/test_workflow_package_to_composable_building_blocks.py::test_workflow_package_to_composable_building_blocks_prompts_keep_step_local_contracts_explicit tests/runtime/test_workflow_to_eval_suite.py::test_workflow_to_eval_suite_prompt_readme_uses_shared_contract_sections tests/runtime/test_workflow_to_eval_suite.py::test_workflow_to_eval_suite_prompts_keep_step_local_contracts_explicit` passed (`47 passed`).
- `/tmp/autoloop-prompt-route-verify-sF91JR/bin/python -m pytest tests/runtime/test_workflow_to_eval_suite.py -q` passed (`29 passed`).
- `/tmp/autoloop-prompt-route-verify-sF91JR/bin/python -m pytest tests/runtime/test_company_operation_to_recursive_improvement_cycle.py tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/runtime/test_workflow_to_eval_suite.py tests/runtime/test_release_candidate_to_go_no_go.py -q` passed (`182 passed`).

## Deduplication / Centralization
- Centralized prompt-body guard ownership in `tests/test_architecture_baseline_docs.py`.
- Centralized workflow compile-cache isolation for helper-driven runtime step tests in `tests/runtime/workflow_contract_helpers.py` instead of duplicating suite-local cache clearing.
- Reused one shared route-model preamble across route-guidance prompt bodies instead of per-workflow wording variants.
