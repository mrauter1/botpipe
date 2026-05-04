# Original intent considered

- Original request: update workflow prompt-body route wording under `workflows/**/prompts/*.md`, update runtime prompt-package tests that still asserted the retired reserved-route phrasing, and add shared baseline coverage so prompt-body route wording is guarded centrally.
- Acceptance checks required:
  - no workflow prompt body contains `Reserved routes`
  - no workflow prompt body describes `blocked` or `failed` as default framework routes
  - representative runtime prompt-package tests pass with the new wording
  - shared baseline coverage fails if retired reserved-route wording returns

# Clarifications / superseding decisions

- The authoritative decisions ledger narrowed the central regression seam to non-README prompt bodies directly, because prior baseline coverage only scanned `docs/workflows/*.md` and prompt `README.md` files.
- The planner then strengthened that seam so it enforces both sides of the shipped route model: positive `question`-only default-control wording and positive authored-`blocked` / authored-`failed` ordinary-application-route wording, plus absence of retired reserved-route wording.
- During implementation review, full-file runtime-suite execution initially failed for reasons outside the prompt-marker assertions. The recorded resolution was a test-only compiler-cache isolation change in `tests/runtime/workflow_contract_helpers.py`, justified because AC-3 required the named runtime suites to pass as full files rather than only as prompt-focused node tests.

# Implemented behavior

- Prompt-body wording is aligned with the shipped route model across the workflow prompt surface. Current repo scan results:
  - `116` non-README prompt bodies under `workflows/*/prompts/*.md`
  - `110` of those contain `## Routes` or `## Route Guidance` and are covered by the shared positive marker assertions
  - `0` prompt bodies contain `Reserved routes` or `Use reserved routes only`
  - `0` prompt bodies contain suspicious `blocked` / `failed` default-route wording outside the approved “ordinary application routes rather than framework defaults” phrasing
- Central regression coverage now exists in `tests/test_architecture_baseline_docs.py::test_workflow_prompt_bodies_use_question_only_runtime_control_wording`, which:
  - scans all non-README prompt bodies for forbidden retired wording
  - requires the positive route-model markers on route-guidance prompt bodies
- Representative runtime prompt-package coverage was updated to assert the new wording in the six requested suites:
  - `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
  - `tests/runtime/test_workflow_portfolio_to_operating_system.py`
  - `tests/runtime/test_workflow_run_history_to_failure_modes.py`
  - `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
  - `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
  - `tests/runtime/test_workflow_to_eval_suite.py`
- Additional validation evidence confirmed the request-level acceptance checks:
  - `rg -n --glob 'workflows/*/prompts/*.md' 'Reserved routes|Use reserved routes only' workflows` returned no matches
  - `/tmp/autoloop-prompt-route-verify-sF91JR/bin/python -m pytest tests/test_architecture_baseline_docs.py::test_workflow_prompt_bodies_use_question_only_runtime_control_wording -q` passed (`1 passed`)
  - `/tmp/autoloop-prompt-route-verify-sF91JR/bin/python -m pytest tests/runtime/test_company_operation_to_recursive_improvement_cycle.py tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/runtime/test_workflow_to_eval_suite.py tests/runtime/test_release_candidate_to_go_no_go.py -q` passed (`183 passed`)

# Unresolved gaps

- No material unresolved gaps found.

# Differences justified by later clarification or analysis

- The implementation touched `tests/runtime/workflow_contract_helpers.py` and added a compile-cache regression in `tests/runtime/test_workflow_to_eval_suite.py` even though the original request was phrased as prompt-body documentation and tests. This difference is justified by later recorded analysis and review:
  - the full-file AC-3 runtime suites initially failed due to helper-driven reuse of stale compiled workflow handlers after monkeypatching
  - the helper change is test-only and does not modify production runtime behavior
  - the additional regression makes the full-suite pass condition deterministic instead of order-dependent
- One extra transitive runtime suite, `tests/runtime/test_release_candidate_to_go_no_go.py`, was included in validation because it shared the same helper seam and was part of the reviewer-confirmed green evidence set. This widened validation, not product scope.

# Recommended next run

- No follow-up implementation is required for this request.
