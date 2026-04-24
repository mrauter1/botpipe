# Implementation Notes

- Task ID: recursive-framework-evolution-20260424t114109-bootstrap
- Pair: implement
- Phase ID: catalog-and-helper-migration
- Phase Directory Key: catalog-and-helper-migration
- Phase Title: Catalog And Helper Migration
- Scope: phase-local producer artifact

## Files changed

- `core/workflow_catalog.py`
- `core/workflow_capabilities.py`
- `runtime/loader.py`
- `runtime/cli.py`
- `runtime/__init__.py`
- `stdlib/portfolio.py`
- `stdlib/adaptation.py`
- `stdlib/refinement.py`
- `stdlib/decomposition.py`
- `tests/runtime/test_compatibility_runtime.py`
- `tests/runtime/test_package_cli.py`
- `tests/unit/test_stdlib_and_extensions.py`

## Symbols touched

- `core.workflow_catalog.WorkflowCatalogEntry`
- `core.workflow_catalog.discover_workflow_catalog`
- `core.workflow_capabilities.WorkflowCapabilityEntry`
- `core.workflow_capabilities.inspect_workflow_capabilities`
- `core.workflow_capabilities.inspect_workflow_reference`
- `core.workflow_capabilities.workflow_capability_payload`
- `runtime.loader.discover_workflow_packages`
- `runtime.loader.inspect_workflow_reference`
- `runtime.loader._load_manifest_package_reference`
- `runtime.cli._handle_workflows_list`
- `runtime.cli._handle_workflows_show`
- `stdlib.portfolio.write_workflow_portfolio_snapshot`
- `stdlib.adaptation.write_selected_workflow_capability_snapshot`
- `stdlib.refinement.write_selected_workflow_authoring_surface`
- `stdlib.decomposition.write_selected_workflow_decomposition_surface`

## Checklist mapping

- Plan item 7 / AC-1: generalized shallow catalog discovery to scan manifest-backed packages plus inferred `flow.py`, `workflow.py`, and top-level single-file workflows without importing modules or requiring `workflows/__init__.py`.
- Plan item 8 / AC-2 / AC-4: deep inspection now runs through the unified resolver, reports authoring shape/source/support paths plus compiled state/parameters/steps/artifacts/sessions/transitions, and keeps the explicit five-branch parameter precedence from the resolver slice.
- AC-3: updated portfolio/adaptation/refinement/decomposition helper seams to consume resolved-root metadata and tolerate optional manifest/spec/doc/prompt/asset/test surfaces, including explicit single-file workflow references.
- Manifest validation regression coverage: kept `workflow.toml` metadata-only and added inferred-shape discovery/deep-inspection tests alongside the existing negative manifest-field checks.

## Preserved invariants

- Root `workflow` shim export surface unchanged.
- `workflow.toml` remains metadata-only; semantic fields still fail validation.
- Existing manifest-backed `workflow.py` packages and package-export checks still work.
- `specs.py` remains ordinary Python; deep inspection only sees it through shallow support-file inference or explicit author imports.

## Intended behavior changes

- `discover_workflow_catalog(...)` now returns authoring-shape-aware entries for manifest packages, inferred `flow.py` packages, inferred legacy `workflow.py` packages, and top-level single-file workflows.
- `inspect_workflow_capabilities(...)` and CLI `workflows show` now expose source path, package folder, authoring shape, state model, parameters model, artifacts, sessions, transitions, and optional support-file paths.
- `workflows list` now includes inferred non-manifest workflows without importing them.
- Stdlib authoring-surface helpers now resolve prompt/asset/doc/test paths from the workflow origin instead of assuming `workflows/<pkg>/workflow.py`.

## Known non-changes

- Scaffold/builder generation is still out of scope for this phase.
- Canonical docs and recursive template prose remain untouched in this slice; related test failures outside the targeted node set still exist because `docs/authoring.md` and recursive template updates belong to later phases.

## Expected side effects

- Duplicate canonical workflow names now fail during shallow discovery even when they come from mixed manifest/inferred shapes.
- Duplicate aliases remain discoverable and are rejected only when a resolver path actually needs to disambiguate them.
- Deep-inspection prompt-path output includes both compiled prompt references and extra prompt files discovered under package-local `prompts/`.

## Validation performed

- `python3 -m py_compile core/workflow_catalog.py core/workflow_capabilities.py runtime/loader.py runtime/cli.py runtime/__init__.py stdlib/portfolio.py stdlib/adaptation.py stdlib/refinement.py stdlib/decomposition.py tests/runtime/test_compatibility_runtime.py tests/runtime/test_package_cli.py tests/unit/test_stdlib_and_extensions.py`
- `.venv/bin/python -m pytest -q tests/runtime/test_compatibility_runtime.py`
- `.venv/bin/python -m pytest -q tests/runtime/test_package_cli.py::test_cli_workflows_show_reports_parameters_and_aliases tests/runtime/test_package_cli.py::test_cli_workflow_resolution_prefers_canonical_names_and_rejects_ambiguous_aliases tests/runtime/test_package_cli.py::test_cli_workflows_list_includes_manifest_and_inferred_workflows_without_imports tests/runtime/test_package_cli.py::test_cli_serializes_typed_workflow_parameters_as_json_safe_values`
- `.venv/bin/python -m pytest -q tests/unit/test_stdlib_and_extensions.py::test_portfolio_helper_writes_workflow_local_catalog_snapshot tests/unit/test_stdlib_and_extensions.py::test_portfolio_helpers_keep_catalog_snapshot_lightweight_and_capability_snapshot_rich tests/unit/test_stdlib_and_extensions.py::test_capability_snapshot_imports_workflows_while_lightweight_portfolio_snapshot_stays_non_importing tests/unit/test_stdlib_and_extensions.py::test_adaptation_helpers_snapshot_one_selected_workflow_without_importing_unrelated_packages tests/unit/test_stdlib_and_extensions.py::test_adaptation_helpers_accept_single_file_workflow_references tests/unit/test_stdlib_and_extensions.py::test_refinement_helper_snapshots_selected_workflow_authoring_surface_via_shared_resolution_and_catalog_seams tests/unit/test_stdlib_and_extensions.py::test_refinement_helper_keeps_optional_authoring_surface_paths_nullable_when_absent tests/unit/test_stdlib_and_extensions.py::test_refinement_helper_accepts_main_workflow_class_references tests/unit/test_stdlib_and_extensions.py::test_decomposition_helper_writes_selected_workflow_identity_authoring_surface_and_compiled_routes tests/unit/test_stdlib_and_extensions.py::test_decomposition_helper_keeps_optional_authoring_paths_nullable_when_absent tests/unit/test_stdlib_and_extensions.py::test_decomposition_helper_reports_empty_parameter_metadata_when_selected_workflow_has_no_params_model tests/unit/test_stdlib_and_extensions.py::test_decomposition_helper_accepts_main_workflow_class_references`
- Broader `tests/runtime/test_package_cli.py` and `tests/unit/test_stdlib_and_extensions.py -k 'portfolio or adaptation or refinement or decomposition'` still hit pre-existing recursive-template and missing-doc assertions outside this phase scope.

## Deduplication / centralization

- Centralized inferred-shape metadata and optional support-file discovery in `core.workflow_catalog`.
- Centralized deep inspection for both cataloged and explicit references in `core.workflow_capabilities.inspect_workflow_reference(...)`.
- Replaced package-only stdlib surface reconstruction with the shared capability contract instead of duplicating directory heuristics in each helper.
