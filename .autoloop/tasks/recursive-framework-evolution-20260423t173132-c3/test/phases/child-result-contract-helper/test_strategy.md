# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c3
- Pair: test
- Phase ID: child-result-contract-helper
- Phase Directory Key: child-result-contract-helper
- Phase Title: Add Child Result Contract Helper
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Helper happy path:
  `tests/unit/test_stdlib_and_extensions.py::test_composition_helpers_delegate_to_ctx_invoke_workflow_and_adopt_child_artifacts`
  validates `require_child_workflow_result(...)` returns the unchanged child result before explicit artifact adoption.
- Wrong child status:
  `tests/unit/test_stdlib_and_extensions.py::test_require_child_workflow_result_rejects_wrong_status`
  asserts the helper rejects non-matching `child_result.status`.
- Wrong terminal route:
  `tests/unit/test_stdlib_and_extensions.py::test_require_child_workflow_result_rejects_wrong_terminal_route`
  asserts the helper checks `child_result.last_event.tag`.
- Missing required child artifact declaration:
  `tests/unit/test_stdlib_and_extensions.py::test_require_child_workflow_result_rejects_missing_required_artifacts`
  asserts a missing required artifact fails fast.
- Missing required child artifact file:
  `tests/unit/test_stdlib_and_extensions.py::test_composition_helpers_reject_declared_child_artifacts_with_missing_source_files`
  asserts missing artifact files fail before parent-local adoption.
- Preserved runtime-backed composition behavior:
  `tests/runtime/test_workspace_and_context.py::test_composition_helpers_keep_child_invocation_explicit_and_adopt_selected_artifacts_into_parent_workflow_folder`
  now exercises `require_child_workflow_result(...)` in the existing runtime composition fixture.
- Preserved `ctx.invoke_workflow(...)` semantics:
  `tests/runtime/test_workspace_and_context.py::test_context_invoke_workflow_accepts_imported_main_workflow_classes_and_records_child_metadata`
  and
  `tests/runtime/test_workspace_and_context.py::test_context_invoke_workflow_by_name_creates_isolated_child_runs_without_inheriting_parent_answers`
  confirm the helper addition did not alter child invocation metadata or parent/child isolation expectations.
- Authoring boundary docs:
  `tests/test_architecture_baseline_docs.py::test_authoring_doc_freezes_the_root_workflow_import_surface`
  and
  `tests/test_architecture_baseline_docs.py::test_authoring_doc_describes_additive_composition_helper_boundary`
  cover export wiring and the explicit non-runtime boundary.

## Preserved invariants checked

- No change to `ctx.invoke_workflow(...)` passthrough behavior.
- No hidden propagation of child `question` / `blocked` routes.
- No widening of runtime-injected control contracts beyond docs/asserted boundary.

## Edge cases and failure paths

- Wrong status
- Wrong terminal route tag
- Missing required artifact key
- Missing required artifact file on disk

## Flake risk and stabilization

- All coverage is filesystem-local and deterministic.
- No network, timing, or nondeterministic ordering dependencies are introduced.
- Runtime proof reuses existing scripted-provider fixtures to keep execution stable.

## Known gaps

- No separate runtime negative-path fixture was added for blocked/paused child routing because that behavior remains explicitly owned by parent workflow code and is already covered by existing invocation-path tests plus the documented boundary.
