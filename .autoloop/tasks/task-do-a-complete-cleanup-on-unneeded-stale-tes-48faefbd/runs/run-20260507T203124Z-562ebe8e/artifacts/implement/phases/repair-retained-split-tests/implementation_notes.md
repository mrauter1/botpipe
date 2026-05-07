# Implementation Notes

- Task ID: task-do-a-complete-cleanup-on-unneeded-stale-tes-48faefbd
- Pair: implement
- Phase ID: repair-retained-split-tests
- Phase Directory Key: repair-retained-split-tests
- Phase Title: Repair retained split tests
- Scope: phase-local producer artifact

## Files changed
- `tests/contract/engine/test_artifacts.py`
- `tests/contract/engine/test_child_workflows.py`
- `tests/contract/engine/test_core_contracts.py`
- `tests/contract/engine/test_errors_and_retries.py`
- `tests/contract/engine/test_hooks.py`
- `tests/contract/engine/test_prompt_context.py`
- `tests/contract/engine/test_routes.py`
- `tests/contract/engine/test_runtime_controls.py`
- `tests/contract/engine/test_sessions.py`
- `tests/contract/engine/test_worklists.py`
- `tests/contract/test_canonical_runtime_contracts.py`
- `tests/strictness/test_no_compat.py`
- `tests/unit/extensions/test_git_and_session_paths.py`
- `tests/unit/optimizer/test_candidate_surfaces.py`
- `tests/unit/optimizer/test_portfolio_helpers.py`
- `tests/unit/optimizer/test_selected_workflow_helpers.py`
- `tests/unit/stdlib/test_authoring_helpers.py`
- `tests/unit/stdlib/test_composition_helpers.py`
- `tests/unit/test_branch_group_context_sessions.py`

## Symbols touched
- Explicit split-test imports for `_chain_hooks`, `_workspace`, `_RenderedTransportStub`, `_ConfigurableRenderedTransport`, `_rendered_provider_with_operation_executor`, `_install_fake_jsonschema_validator`, `_RecordingExtension`, `_ApprovalInput`, `_load_replay_store`, `_git`, `_build_lifecycle_context`, `_assert_mapping_contains`, `_write_catalog_workflow`, `_write_run_history_record`, `_write_runtime_valid_catalog_workflow`, `_write_single_file_runtime_workflow`, `_write_task_operation_record`, `_ExampleModel`, `_build_child_result`, `_capture_child_invocation`
- Local synthetic `RefinementParameters` and `DecompositionParameters` in `tests/unit/stdlib/test_authoring_helpers.py`
- Local `PACKAGE_ROOT` in `tests/contract/engine/test_core_contracts.py`
- Maintained assertions in `tests/strictness/test_no_compat.py`, `tests/contract/test_canonical_runtime_contracts.py`, and `tests/unit/test_branch_group_context_sessions.py`

## Checklist mapping
- Explicit private-helper imports for retained split modules: complete
- Remove repo-owned workflow-package params imports from retained stdlib tests: complete
- Realign stale strictness/runtime assertions to maintained behavior: complete
- Run requested pytest target: complete

## Assumptions
- Maintained `question`-route required-write semantics are defined by retained engine contract coverage, not by the deleted monolith contract file.
- `WorkflowInputView.message` is an intentional supported surface because it is exposed by `autoloop/core/context.py` and covered by other retained tests.

## Preserved invariants
- No production code outside `tests/` changed.
- No deleted parity/docs/workflow-package runtime suites were restored.
- Shared `_shared.py` modules stayed private; no `__all__` changes or helper renames were introduced.

## Intended behavior changes
- Retained split tests now import required private helpers explicitly instead of relying on `import *` to leak underscore-prefixed names.
- `tests/unit/stdlib/test_authoring_helpers.py` covers selected-workflow parameter inheritance with local synthetic models instead of repo-owned workflow packages.
- Strictness and retained contract/unit assertions now match the maintained split layout and current runtime semantics.

## Known non-changes
- No workflow-package runtime coverage was reintroduced under `tests/`.
- No production validation, routing, context, or provider behavior was modified.

## Expected side effects
- Retained split suites remain green after the cleanup while shared helper visibility stays unchanged.

## Validation performed
- `rg -n "autoloop\\.workflows\\..*params" tests` returned no matches.
- `.venv/bin/python -m pytest tests/strictness/test_no_compat.py tests/contract tests/unit -q` passed (`785 passed, 1 warning`).

## Deduplication / centralization decisions
- Kept existing shared helpers in place and added only explicit imports at split call sites; no new shared abstraction was introduced.
