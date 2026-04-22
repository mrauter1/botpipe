# Implementation Notes

- Task ID: recursive-framework-evolution-20260422t165825-bootstrap
- Pair: implement
- Phase ID: workflow-package-foundation
- Phase Directory Key: workflow-package-foundation
- Phase Title: Workflow Package Foundation
- Scope: phase-local producer artifact

## Files changed

- `runtime/loader.py`
- `runtime/__init__.py`
- `workflows/__init__.py`
- `workflows/autoloop_v1/__init__.py`
- `workflows/autoloop_v1/workflow.py`
- `workflows/autoloop_v1/workflow.toml`
- `workflows/autoloop_v1/prompts/README.md`
- `workflows/autoloop_v1/assets/.gitkeep`
- `workflows/autoloop_v1/conventions.py`
- `workflows/autoloop_v1/parity.py`
- `docs/architecture.md`
- `docs/authoring.md`
- `tests/conftest.py`
- `tests/runtime/test_compatibility_runtime.py`
- `tests/runtime/test_workflow_integration_parity.py`
- `tests/strictness/test_no_compat.py`
- `tests/test_architecture_baseline_docs.py`
- `.autoloop/tasks/recursive-framework-evolution-20260422t165825-bootstrap/decisions.txt`

## Symbols touched

- `discover_workflow_packages`
- `resolve_workflow_package`
- `resolve_workflow_reference`
- `load_workflow_package_class`
- `load_compiled_workflow_package`
- `WorkflowPackage`
- `ResolvedWorkflow`
- `WorkflowManifestError`
- `WorkflowDiscoveryError`
- `AutoloopV1`

## Checklist mapping

- Milestone 1 / workflow package foundation:
  - converted repo-root `workflows/` into a package-of-packages shape
  - added metadata-only `workflow.toml` discovery and alias resolution
  - enforced package `__init__.py` main-class re-export and optional `Parameters` export contract
  - added repo scaffolding for `workflows/autoloop_v1/`
  - replaced stale docs/tests that treated internal modules or legacy helper modules as the public contract
- Deferred by design to later phases:
  - public CLI cutover
  - task -> workflow -> runs workspace migration
  - `ctx.invoke_workflow(...)`
  - full Autoloop-v1 runtime/parity migration

## Assumptions

- The current repo root and its parent are both valid import roots during local authoring/testing, so the strict top-level `workflow` and `workflows` packages must remain directly importable.
- The existing raw loader path is still needed by non-phase tests and runtime code until later CLI/runtime cutover work lands.

## Preserved invariants

- The root `workflow` shim remains the strict authoring surface.
- `workflow.toml` stays metadata-only and does not define execution semantics.
- Legacy raw loading behavior was not removed from runtime code in this phase.
- Existing Autoloop-v1 parity code was preserved, but moved under the workflow package namespace rather than deleted.

## Intended behavior changes

- Workflow discovery now has a strict manifest-based package contract rooted at `<root>/workflows/*/workflow.toml`.
- Repo-root `workflows/` no longer re-exports a helper runner from its package root.
- `workflows/autoloop_v1/` is now a real workflow package with direct-import support.

## Known non-changes

- `run_workflow(...)` still uses the legacy raw target execution path.
- Workspace layout, resume semantics, and prompt resolution remain unchanged in this phase.
- The Autoloop-v1 package shell is scaffolding only; parity runtime wiring remains later work.

## Expected side effects

- Future CLI/runtime phases can resolve workflows by canonical name, alias, or imported workflow class without adding new manifest DSL fields.
- Tests and docs now pin the package authoring/discovery contract instead of missing legacy files.

## Deduplication / centralization

- Package manifest parsing, alias resolution, and package export enforcement were centralized in `runtime/loader.py` instead of duplicating discovery logic across tests or future CLI code.
- Existing Autoloop-v1 support code was moved into its workflow package so later migration work can refine package-local parity in place.

## Validation performed

- `python3 -m compileall workflow workflows runtime core tests`
- `unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_PREFIX GIT_CEILING_DIRECTORIES && PYTHONPATH="$(dirname "$PWD"):$PWD" /tmp/autoloop-phase1-venv/bin/python -m pytest -q tests/runtime/test_compatibility_runtime.py tests/runtime/test_workflow_integration_parity.py tests/strictness/test_no_compat.py tests/test_architecture_baseline_docs.py`
- `unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_PREFIX GIT_CEILING_DIRECTORIES && PYTHONPATH="$(dirname "$PWD"):$PWD" /tmp/autoloop-phase1-venv/bin/python -m pytest -q tests/unit/test_validation.py tests/unit/test_primitives_and_stores.py tests/unit/test_stdlib_and_extensions.py tests/contract/test_engine_contracts.py tests/runtime/test_optional_extensions.py`
- `unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_PREFIX GIT_CEILING_DIRECTORIES && PYTHONPATH="$(dirname "$PWD"):$PWD" /tmp/autoloop-phase1-venv/bin/python -m pytest -q`
