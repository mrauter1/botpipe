# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t120129-bootstrap
- Pair: implement
- Phase ID: docs-strictness-and-regression-proof
- Phase Directory Key: docs-strictness-and-regression-proof
- Phase Title: Harden Docs And Regression Guards
- Scope: phase-local producer artifact

## Files changed

- `docs/architecture.md`
- `docs/authoring.md`
- `tests/test_architecture_baseline_docs.py`
- `tests/strictness/test_no_compat.py`
- `tests/runtime/test_package_cli.py`

## Symbols touched

- Architecture doc sections: `Provider Selection`, `Resumability`, `Recursive Operation`
- Authoring doc sections: `Runtime Config And Provider Selection`, `Sessions And Resumability`, `Recursive And Package-Only Guidance`
- Strictness helper: `_iter_active_text_files`
- Strictness guard: `test_active_tree_does_not_reintroduce_removed_compatibility_surfaces`
- Test guard constants for removed compatibility tokens in doc/package-cli tests

## Checklist mapping

- AC-1: documented typed provider selection, generic provider flags, canonical `session_id` resumability, and package-only recursive execution in maintained docs
- AC-2: expanded baseline/strictness coverage to forbid removed compatibility surfaces across the maintained active tree and wrapper/template guards
- AC-3: ran targeted suites plus full suite and confirmed clean pass

## Assumptions

- Maintained docs scope for this phase is `docs/architecture.md` and `docs/authoring.md`
- Historical narrative docs such as `docs/refactor.md`, root `refactor.md`, and task artifacts remain out of strictness scan scope

## Preserved invariants

- No runtime, provider, session-store, or wrapper behavior changed in this phase
- Public contract remains package CLI, typed provider selection, and canonical `session_id` resumability

## Intended behavior changes

- Maintained docs now explicitly describe provider selection through typed config plus `--provider` / `--model` / `--model-effort`
- Maintained docs now describe resumability through opaque `session_id` plus `provider_metadata`
- Strictness now fails if removed compatibility surfaces reappear in maintained active source/docs/templates/tests

## Known non-changes

- Did not rewrite historical design docs or task-local artifacts that still discuss the removed compatibility surfaces
- Did not add shared test helper modules; kept guard constants local to touched tests to minimize churn

## Expected side effects

- Guard tests use split token literals so repo-wide scans can include `tests/` without false positives from the assertions themselves

## Validation performed

- `.venv/bin/pytest tests/test_architecture_baseline_docs.py tests/strictness/test_no_compat.py`
- `.venv/bin/pytest tests/runtime/test_package_cli.py tests/runtime/test_compatibility_runtime.py tests/runtime/test_workflow_integration_parity.py`
- `.venv/bin/pytest`

## Validation results

- Targeted docs/strictness suite: passed
- Targeted runtime/package/parity suite: passed
- Full suite: `125 passed`
