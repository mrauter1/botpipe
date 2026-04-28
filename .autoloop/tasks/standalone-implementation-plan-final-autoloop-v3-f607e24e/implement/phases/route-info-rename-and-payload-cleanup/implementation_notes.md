# Implementation Notes

- Task ID: standalone-implementation-plan-final-autoloop-v3-f607e24e
- Pair: implement
- Phase ID: route-info-rename-and-payload-cleanup
- Phase Directory Key: route-info-rename-and-payload-cleanup
- Phase Title: Route-Info Rename And Payload Cleanup
- Scope: phase-local producer artifact

## Files changed

- `stdlib/__init__.py`
- `stdlib/route_infos.py`
- `stdlib/contracts.py` (deleted)
- `core/workflow_catalog.py`
- `core/workflow_capabilities.py`
- `runtime/cli.py`
- `tests/unit/test_stdlib_and_extensions.py`
- `tests/runtime/test_compatibility_runtime.py`

## Symbols touched

- `review_gate_infos`, `publication_gate_infos`
- `WorkflowCatalogEntry`
- `WorkflowCapabilityEntry`
- `workflow_capability_payload`
- `selected_workflow_authoring_surface_payload`
- `selected_workflow_decomposition_surface_payload`
- `_spec_paths`
- `_support_spec_paths`

## Checklist mapping

- Step 4.1-4.4: renamed stdlib route-info module/functions and updated imports/tests.
- Step 5.1-5.5: removed `contracts_path` / `contracts_path_repo_relative`, folded `contracts.py` into `spec_paths`, and updated capability/authoring/decomposition expectations.
- Step 6.2: added assertions that old helper names/module path are gone from the touched public/test surfaces.

## Intended behavior changes

- `stdlib.contracts` is gone; callers must import `stdlib.route_infos`.
- `review_gate_contracts` / `publication_gate_contracts` are gone; callers must use `review_gate_infos` / `publication_gate_infos`.
- Catalog/capability/CLI payloads no longer emit `contracts_path` fields.
- `contracts.py` remains discoverable only through `spec_paths`, `editable_paths`, and repo-relative spec-path payloads.

## Preserved invariants

- `contracts.py` stays editable when present because `editable_paths` still includes all `spec_paths`.
- Workflow discovery semantics outside spec/support-file enumeration were not changed.
- `legacy_workflow_path` handling remains unchanged in this phase.

## Known non-changes

- No runtime workflow resolution logic changed beyond support-file discovery.
- No docs/docstring cleanup beyond the touched module rename was attempted in this phase.
- No compatibility alias was kept for the removed stdlib helper names or module.

## Validation performed

- `python3 -m compileall stdlib core runtime tests/runtime/test_compatibility_runtime.py tests/unit/test_stdlib_and_extensions.py`
- `.venv/bin/python -m pytest tests/runtime/test_compatibility_runtime.py tests/unit/test_stdlib_and_extensions.py -q`
- `.venv/bin/python -m pytest tests/runtime/test_workflow_reference_resolution.py -q`
- `.venv/bin/python` smoke script covering catalog discovery, capability payloads, authoring/decomposition payloads, and stdlib route-info helpers

## Assumptions and side effects

- Phase scope allowed test updates that assert removal of public fields and renamed stdlib helpers.
- The strictness phase can build on the new absence assertions instead of re-checking this payload shape from scratch.
