# Implementation Notes

- Task ID: objective-implement-workflow-installation-and-di-c328695f
- Pair: implement
- Phase ID: catalog-root-refactor
- Phase Directory Key: catalog-root-refactor
- Phase Title: Refactor Workflow Search Roots And Catalog
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/workflow_catalog.py`
- `autoloop/runtime/loader.py`
- `autoloop/core/workflow_capabilities.py`
- `autoloop/workflows/__init__.py`
- `tests/runtime/test_workflow_catalog_roots.py`
- `.../decisions.txt`

## Symbols touched
- `WorkflowSearchRoot`
- `workspace_workflows_root`
- `package_workflows_root`
- `workflow_search_roots`
- `read_workflow_manifest`
- `discover_workflow_catalog`
- `WorkflowCatalogEntry`
- `discover_workflow_packages`
- `resolve_workflow_package`
- `resolve_workflow_reference`
- `_resolve_named_reference`
- `_resolve_path_reference`
- `_resolve_catalog_entry_reference`
- `_resolve_manifest_path_reference`
- `_load_isolated_python_module`
- `load_workflow_package_contract`

## Checklist mapping
- Plan milestone 1 / AC-1: implemented canonical workspace/package roots, missing-root tolerance, non-directory root errors, effective catalog assembly, and optional shadowed entry reporting.
- Plan milestone 1 / AC-2: bare-name resolution now uses the catalog only; unknown bare references report workspace root plus searched roots; explicit `.py` and `.toml` paths bypass catalog precedence.
- Plan milestone 1 / AC-3: workspace directory workflows, workspace single-file workflows, and package directory workflows emit exact `source_root_kind` values with package import metadata only for package roots.
- Plan milestone 1 / AC-4: manifest parsing now validates `module` and `class`; manifest-backed explicit and catalog resolution covers `flow.py` then `workflow.py` fallback and class-selection failures.
- Deferred by phase contract: built-in workflow relocation, CLI help/scaffold/list/show updates, runtime metadata persistence expansion, and packaging/wheel verification.

## Assumptions
- Phase-local tests may inject a temporary `autoloop` package search path because built-in workflows have not been relocated under `autoloop/workflows` yet.
- Discovery should fully remove bare-name compatibility for `{workspace}/workflows`, even though unrelated legacy tests elsewhere may still target that older root.

## Preserved invariants
- Explicit filesystem path references remain supported.
- Workspace workflow loading still avoids adding `.autoloop` to `sys.path`.
- Package workflow loading continues to use normal Python imports when package metadata is available.

## Intended behavior changes
- Bare workflow discovery now scans only `{workspace}/.autoloop/workflows` and `autoloop/workflows`.
- Workspace names and aliases shadow package names and aliases without cross-tier ambiguity failures.
- Explicit `.toml` references are first-class workflow references.

## Known non-changes
- No built-in workflows were moved from the top-level `workflows/` tree in this phase.
- CLI JSON/help/scaffold surfaces still need follow-up work in later phases.
- Runtime `workflow.json` / `run.json` origin payload expansion was not changed in this phase.

## Expected side effects
- Focused legacy tests that still assume bare discovery from `{workspace}/workflows` will need migration in later phases.
- `autoloop.workflows` now exists as a namespace package, enabling package-root imports once built-ins move under it.

## Validation performed
- `.venv_phase/bin/python -m py_compile autoloop/core/workflow_catalog.py autoloop/runtime/loader.py autoloop/core/workflow_capabilities.py autoloop/workflows/__init__.py tests/runtime/test_workflow_catalog_roots.py`
- `.venv_phase/bin/python -m pytest tests/runtime/test_workflow_catalog_roots.py -q`
- `.venv_phase/bin/python - <<'PY' ... discover_workflow_catalog(Path('.').resolve()) ... PY`

## Deduplication / centralization
- Centralized authoritative root enumeration and precedence in `discover_workflow_catalog(...)`.
- Centralized bare-reference selection in loader helpers instead of probing filesystem candidates directly from `_resolve_named_reference`.
