# Test Author ↔ Test Auditor Feedback

- Task ID: framework-authoring-flexibility-change-spec-goal-2ee572cd
- Pair: test
- Phase ID: align-runtime-fixtures-and-revalidate
- Phase Directory Key: align-runtime-fixtures-and-revalidate
- Phase Title: Align Fixtures And Revalidate
- Scope: phase-local authoritative verifier artifact

- Added `test_temporary_workspace_workflow_packages_keep_ctx_only_python_step_handlers` in `tests/runtime/test_workspace_and_context.py` to pin the fixture authoring contract directly: phase-local `@python_step` package writers must emit `def ...(ctx):`, while typed child output fixtures still keep `build_output(state, ctx)`.
