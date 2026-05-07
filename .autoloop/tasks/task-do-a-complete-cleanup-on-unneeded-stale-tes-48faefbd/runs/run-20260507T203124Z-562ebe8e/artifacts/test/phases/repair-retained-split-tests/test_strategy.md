# Test Strategy

- Task ID: task-do-a-complete-cleanup-on-unneeded-stale-tes-48faefbd
- Pair: test
- Phase ID: repair-retained-split-tests
- Phase Directory Key: repair-retained-split-tests
- Phase Title: Repair retained split tests
- Scope: phase-local producer artifact

## Behavior-to-coverage map

- Private shared-helper imports in retained split files:
  Covered by the requested `tests/contract` and `tests/unit` target; those files now execute with explicit imports instead of relying on underscore leakage from `import *`.
- Repo-owned workflow-package params must stay out of retained shared tests:
  Covered by `tests/unit/stdlib/test_authoring_helpers.py::test_workflow_specific_parameter_models_keep_inherited_selected_workflow_validation` and the added AST-based source guard `test_retained_stdlib_authoring_test_stays_free_of_repo_owned_workflow_package_params`.
- Split-layout strictness expectations:
  Covered by `tests/strictness/test_no_compat.py::test_removed_compatibility_scan_scope_covers_maintained_tree_only`.
- Maintained question-route required-write semantics:
  Covered by `tests/contract/test_canonical_runtime_contracts.py` and reinforced by retained engine contract tests under `tests/contract/engine`.
- Maintained `WorkflowInputView.message` surface for branch/fan-in contexts:
  Covered by `tests/unit/test_branch_group_context_sessions.py::test_branch_and_fan_in_contexts_preserve_parent_request_snapshot`.

## Preserved invariants checked

- Shared `_shared.py` modules remain private; no `__all__` widening is required.
- No retained shared test imports `autoloop.workflows.*.params`.
- No production-code changes are needed for the retained assertions to pass.

## Edge cases and failure paths

- Source-level ownership regression:
  The AST-based guard fails only on real `ImportFrom` nodes targeting the forbidden workflow-package `params` modules, avoiding false positives from string literals.
- Runtime semantic drift:
  The retained contract and branch-context tests still fail if question-route write requirements or `ctx.input.message` behavior regress.

## Flake risk / stabilization

- No network, timing, or nondeterministic ordering added.
- Source-scan coverage uses local file reads plus AST parsing only.

## Known gaps

- Explicit private-helper imports are exercised indirectly by the retained target rather than by a dedicated import-structure test for every split module.
