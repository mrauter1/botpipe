# Test Strategy

- Task ID: recursive-framework-evolution-20260422t165825-bootstrap
- Pair: test
- Phase ID: workflow-package-foundation
- Phase Directory Key: workflow-package-foundation
- Phase Title: Workflow Package Foundation
- Scope: phase-local producer artifact

## Behavior-to-test coverage

- AC-1 workflow package discovery and metadata-only manifests:
  - `tests/runtime/test_compatibility_runtime.py::test_discover_workflow_packages_reads_metadata_without_importing_workflow_modules`
  - `tests/runtime/test_compatibility_runtime.py::test_discovery_rejects_manifest_execution_fields`
  - `tests/runtime/test_compatibility_runtime.py::test_resolve_workflow_package_prefers_canonical_name_and_rejects_ambiguous_aliases`
  - `tests/runtime/test_workflow_integration_parity.py::test_repo_workflow_package_name_resolution_uses_explicit_root_without_repo_root_on_syspath`
- AC-2 package `__init__.py` export contract and imported-class resolution:
  - `tests/runtime/test_compatibility_runtime.py::test_resolve_workflow_reference_enforces_package_reexports_and_optional_parameters`
  - `tests/runtime/test_compatibility_runtime.py::test_resolve_workflow_reference_requires_parameters_to_appear_in_all`
  - `tests/runtime/test_compatibility_runtime.py::test_resolve_workflow_reference_accepts_imported_main_workflow_class`
  - `tests/runtime/test_workflow_integration_parity.py::test_repo_workflow_package_can_be_imported_and_compiled_directly`
- AC-3 strict public authoring surface and docs:
  - `tests/strictness/test_no_compat.py`
  - `tests/test_architecture_baseline_docs.py`

## Preserved invariants checked

- Discovery reads `workflow.toml` metadata without importing workflow code.
- Canonical workflow names beat aliases, and ambiguous aliases fail instead of guessing.
- Repo-root package-name resolution works from a neutral cwd when the caller passes `REPO_ROOT`.
- The explicit-root import helper restores `sys.path` after resolution and does not leak repo-root import state.
- The root `workflow` shim and `workflow.primitives` shim remain strict and do not re-expose legacy/internal symbols.

## Edge cases and failure paths

- Manifest execution fields are rejected because `workflow.toml` is metadata-only.
- Missing `__init__.py` re-export for the main workflow class fails resolution.
- Exported `Parameters` must also appear in `__all__`.
- Ambiguous aliases fail deterministically.

## Stabilization notes

- Tests use temp package roots and explicit `monkeypatch` cleanup for `cwd`, `sys.path`, and imported `workflows.*` modules.
- Validation should continue unsetting inherited `GIT_*` environment variables for git-sensitive tests in this repo.

## Known gaps

- CLI subcommand behavior is intentionally out of scope for this phase and remains uncovered here.
- Workspace layout, prompt-root resolution, and Autoloop-v1 runtime parity are deferred to later phases.
