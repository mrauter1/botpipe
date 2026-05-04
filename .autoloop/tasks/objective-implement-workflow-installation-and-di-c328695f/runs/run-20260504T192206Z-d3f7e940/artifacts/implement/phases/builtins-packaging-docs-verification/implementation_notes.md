# Implementation Notes

- Task ID: objective-implement-workflow-installation-and-di-c328695f
- Pair: implement
- Phase ID: builtins-packaging-docs-verification
- Phase Directory Key: builtins-packaging-docs-verification
- Phase Title: Relocate Built-Ins, Package Assets, And Close Verification
- Scope: phase-local producer artifact

## Files Changed

- Packaging and install surface: `pyproject.toml`, `MANIFEST.in`, `autoloop/workflows/__init__.py`
- Built-in workflow relocation: `autoloop/workflows/*/` packages moved from repo-root `workflows/*/`
- Runtime/loader support: `autoloop/core/descriptors.py`
- Docs and recursive templates: `docs/architecture.md`, `docs/authoring.md`, `docs/workflows/*.md`, `recursive_autoloop/run_recursive_autoloop_templates/*.md.tmpl`
- Tests: `tests/runtime/test_package_cli.py`, `tests/runtime/test_runtime_cli_metadata_integration.py`, `tests/runtime/test_wheel_packaging_smoke.py`, `tests/runtime/test_*workflow*.py`, `tests/test_architecture_baseline_docs.py`, `tests/strictness/test_no_compat.py`

## Symbols Touched

- `effective_parameters_model`
- package script entry point and setuptools package-data configuration in `pyproject.toml`
- package workflow namespace `autoloop.workflows`

## Checklist Mapping

- Milestone 3 / built-in relocation: completed by moving built-ins under `autoloop/workflows/<workflow_id>/` and updating built-in import references to `autoloop.workflows.*`
- Milestone 3 / export validation readiness: completed by preserving package `__init__.py` exports and `__all__` under relocated built-ins
- Milestone 3 / repo-asset depth fixes: completed by updating built-in workflow-relative doc/instruction/test paths after the deeper package location
- Milestone 3 / packaging metadata: completed by adding `project.scripts`, package discovery, package-data, runtime dependency declaration, and `MANIFEST.in`
- Milestone 3 / docs: completed by documenting `autoloop/workflows/`, `.autoloop/workflows/`, workspace precedence, and the absence of `{workspace}/workflows/` discovery
- Milestone 3 / verification: completed with focused CLI/runtime/doc tests plus wheel build/install smoke coverage

## Assumptions

- Existing built-in workflow package internals remain valid after relocation if import paths and package-folder-relative repo references are updated.
- The runtime should continue to support `workflow.py` for built-ins even though scaffolds prefer `flow.py`.

## Preserved Invariants

- Bare workflow discovery remains limited to package and workspace roots only.
- Explicit filesystem path resolution remains separate from catalog precedence.
- Runtime metadata continues to reference workflow sources in place rather than copying packages into run state.

## Intended Behavior Changes

- Built-in workflows now import from `autoloop.workflows.<workflow_id>`.
- Empty workspaces can discover package-installed workflows from the installed wheel.
- Default simple-workflow `EmptyParams` no longer masks exported `params.py` parameter models.

## Known Non-Changes

- No legacy compatibility was added for bare-name discovery from `{workspace}/workflows/`.
- No additional workflow source kinds were introduced beyond `"workspace"` and `"package"`.

## Expected Side Effects

- CLI `workflows list` in non-empty workspaces now includes package workflows alongside workspace workflows unless shadowed.
- Wheel contents now include built-in workflow manifests, prompts, assets, and optional support files under `autoloop/workflows/`.

## Validation Performed

- `python -m pytest -q tests/runtime/test_package_cli.py`
- `python -m pytest -q tests/runtime/test_workflow_catalog_roots.py tests/runtime/test_runtime_cli_metadata_integration.py tests/test_architecture_baseline_docs.py tests/strictness/test_no_compat.py tests/runtime/test_wheel_packaging_smoke.py`
- `python -m build` through `tests/runtime/test_wheel_packaging_smoke.py`
- Clean venv install smoke via `tests/runtime/test_wheel_packaging_smoke.py`, including `autoloop --help`, empty-workspace listing, and packaged asset access

## Deduplication / Centralization Decisions

- Kept the loader fix local to `effective_parameters_model` so package/workspace `params.py` discovery works everywhere without duplicating special-case logic in CLI or capability inspection.
