# Test Strategy

- Task ID: goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6
- Pair: test
- Phase ID: runtime-validation-and-regression-checks
- Phase Directory Key: runtime-validation-and-regression-checks
- Phase Title: Validate runtime behavior and guard regressions
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Selector/progress runtime happy paths:
  `tests/runtime/test_progress_worklists.py` covers default `all`, explicit `single`, `up_to`, and inclusive `from_to` execution with persisted status updates.
- Selector/progress failure and edge paths:
  `tests/runtime/test_progress_worklists.py` covers invalid `from_to` bounds and skipped-status acceptance only under an opt-in policy.
- Adjacent repo-local workflow regression surface:
  `tests/runtime/test_workflow_catalog_roots.py` now covers repo-local `<repo>/workflows` discovery defaults, repo-level runtime test discovery, and `workflows.*` import refresh across two different repo roots in one process.
- Adjacent helper and context invariants:
  `tests/unit/test_stdlib_and_extensions.py`, `tests/unit/test_primitives_and_stores.py`, and `tests/runtime/test_workspace_and_context.py` remain the required regression commands for repo-root, snapshot, and workflow-resolution behavior.

## Preserved invariants checked

- No legacy selector aliases or legacy progress-board shapes were normalized back into expectations.
- Workspace-scoped helper outputs stay rooted at repo-local `workflows/` and `docs/workflows/`.
- Cross-test module state is stabilized with explicit `workflows.*` / `autoloop.workflows.*` cleanup fixtures.

## Edge cases and failure paths

- Missing title/description in repo-local manifests still resolve via defaults only for the repo-local `workflows/` search root.
- Cached `workflows.repo_demo.*` modules must not bleed from one temp repo root into another within the same process.
- Invalid selector range handling remains covered by runtime execution tests, not by mocked unit assertions alone.

## Validation

- `.venv/bin/pytest tests/runtime/test_workflow_catalog_roots.py`
  Result: 20 passed.
- `.venv/bin/pytest tests/unit/test_worklist_selectors.py tests/unit/test_stdlib_progress_worklists.py tests/runtime/test_progress_worklists.py`
  Result: 49 passed.
- `.venv/bin/pytest tests/unit/test_stdlib_and_extensions.py tests/unit/test_primitives_and_stores.py tests/runtime/test_workspace_and_context.py`
  Result: 173 passed.

## Known gaps

- This phase did not add full-suite coverage beyond the focused and adjacent commands named in the request.
- The new repo-local package regression test aligns with the supported package shape that includes `workflows/__init__.py`; namespace-package-only repo roots remain outside this phase contract.
