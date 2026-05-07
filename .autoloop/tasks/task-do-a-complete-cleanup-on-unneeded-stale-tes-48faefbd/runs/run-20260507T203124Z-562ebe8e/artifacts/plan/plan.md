# Retained Split Test Cleanup Plan

## Objective
Return the required `tests/` validation target to green without restoring removed monolith entrypoints, changing production code outside `tests/`, or reintroducing repo-owned workflow-package dependencies into retained shared tests.

## Confirmed findings
- The requested validation target currently fails in `243` tests. The dominant regression is `NameError` from split files that still rely on `from ... import *` while consuming underscore-prefixed helpers from `_shared.py`.
- `tests/strictness/test_no_compat.py` still asserts the deleted `tests/contract/test_engine_contracts.py` path.
- The remaining direct imports of repo-owned workflow-package params within retained shared tests are the two imports in `tests/unit/stdlib/test_authoring_helpers.py`.
- Shared helper modules currently have no `__all__`; widening their exports would make private helpers public and would spread the split-specific regression into the shared module contract.
- Three residual failures inside the same validation target are stale test expectations, not a second production-code scope: `tests/contract/test_canonical_runtime_contracts.py` still expects `question` routes to inherit step required writes even though maintained contract coverage already expects `question: ()`, and `tests/unit/test_branch_group_context_sessions.py` still expects `child.input` to hide `.message` even though `WorkflowInputView` exposes it in `autoloop/core/context.py`.

## Implementation slice
One coherent phase is sufficient because every known failure that must move for this task remains inside `tests/`: split-import repairs, test-local synthetic parameter models, stale strictness assertions, and stale retained assertions that need to be realigned with already-maintained runtime semantics.

### Milestone 1: Repair retained split tests
- Replace wildcard-only reliance on private shared helpers with explicit named imports in retained split files that use underscore-prefixed helpers.
- Contract files needing explicit private-helper imports: `tests/contract/engine/test_artifacts.py`, `test_child_workflows.py`, `test_core_contracts.py`, `test_errors_and_retries.py`, `test_hooks.py`, `test_prompt_context.py`, `test_routes.py`, `test_runtime_controls.py`, `test_sessions.py`, `test_worklists.py`.
- Unit files needing explicit private-helper imports: `tests/unit/extensions/test_git_and_session_paths.py`, `tests/unit/optimizer/test_candidate_surfaces.py`, `test_portfolio_helpers.py`, `test_selected_workflow_helpers.py`, `tests/unit/stdlib/test_authoring_helpers.py`, `test_composition_helpers.py`.
- Keep `_shared.py` modules private. Do not add `__all__` entries or rename helpers solely to preserve `import *`.
- Update `tests/unit/stdlib/test_authoring_helpers.py` to validate inherited parameter-model behavior using local synthetic parameter models or fixtures instead of `autoloop.workflows.*.params`.
- Update `tests/strictness/test_no_compat.py` so its maintained scan assertions reflect the retained split layout and no longer require the removed monolith file.
- Update `tests/contract/test_canonical_runtime_contracts.py` so its retained provider-contract assertions match the maintained `question`-route required-write semantics already covered by `tests/contract/engine/test_core_contracts.py` and `tests/contract/engine/test_routes.py`.
- Update `tests/unit/test_branch_group_context_sessions.py` so its retained branch/fan-in input-view assertion matches the current `WorkflowInputView.message` surface in `autoloop/core/context.py`.

## Interface and compatibility notes
- Scope is limited to `tests/`; no production modules, workflow packages, docs suites, parity suites, or deleted monolith files are to be restored.
- Test intent must stay the same: shared helpers remain reusable, split files become explicit about private helper dependencies, and workflow-parameter normalization coverage remains local to the retained stdlib test file.
- Any synthetic parameter models added in `tests/unit/stdlib/test_authoring_helpers.py` should cover the same normalization/inheritance behaviors currently asserted for refinement and decomposition parameter types.
- The residual canonical-runtime and branch-context edits are test-alignment only. They must not change production contracts; they should reflect semantics already established in maintained runtime code and retained contract coverage.

## Regression controls
- Preserve existing retained file layout; only change imports, local synthetic test scaffolding, and the strictness scan assertion.
- Before updating the three residual stale assertions, cross-check them against maintained references in `autoloop/core/context.py`, `tests/contract/engine/test_core_contracts.py`, and `tests/contract/engine/test_routes.py`; if those references do not support the current runtime behavior, stop because a production fix would exceed the `tests/`-only scope.
- Verify no retained shared test imports `autoloop.workflows.*.params` after the cleanup.
- Re-run `.venv/bin/python -m pytest tests/strictness/test_no_compat.py tests/contract tests/unit -q`.

## Risk register
- Risk: broad import edits accidentally hide missing dependencies or shadow public names. Mitigation: import only the specific private helpers each split file uses and leave public shared names untouched.
- Risk: synthetic parameter models drift from the validation semantics under test. Mitigation: subclass the same retained base parameter models and assert the same trimming, deduping, optional-field, and inherited selected-workflow validation behavior.
- Risk: strictness expectations drift again if tied to deleted monolith paths. Mitigation: assert against retained split paths or other stable maintained-tree members that survive the cleanup.
- Risk: updating the three residual tests could accidentally bless a real runtime regression. Mitigation: treat them as stale-test cleanup only when they agree with the maintained runtime and contract references above; otherwise escalate the scope conflict instead of rewriting the assertions.

## Rollback
- Revert only the touched `tests/` files if the targeted suite regresses.
- Do not reintroduce deleted `tests/contract/test_engine_contracts.py` or any removed parity/docs/workflow-package runtime suites as a rollback mechanism.
