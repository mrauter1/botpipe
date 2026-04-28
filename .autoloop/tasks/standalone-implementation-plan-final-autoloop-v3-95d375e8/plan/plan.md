# Final Autoloop v3 Cleanup Fixes Plan

## Intent Boundary

Treat the request snapshot as the implementation contract. This is a greenfield cleanup pass with explicit behavior breaks:

- delete `workflow/` completely; do not leave a shim or hard-fail alias
- remove active `legacy_*` / compatibility naming where the request specifies a rename
- delete `ResolvedWorkflow.package` rather than preserving an alias
- keep `workflow_package` as the current authoring-shape value
- do not add `autoloop eject`, source expansion, migration generators, or workflow-step handler refactors

The only runtime behavior change is in provider retry feedback for invalid structured route payloads. Everything else is a surface cleanup, rename, deletion, or regression guard.

## Pre-Change Audit Summary

### Primary edit surfaces already confirmed in the repo

1. Provider retry feedback and tests
   - `core/providers/retries.py`
   - `tests/unit/test_provider_retries.py`
2. Public exports and primitive import roots
   - `autoloop/simple.py`
   - `autoloop/__init__.py`
   - `tests/unit/test_simple_surface.py`
   - `tests/unit/test_primitives_and_stores.py`
3. Workflow deletion and rename fallout
   - `core/validation.py`
   - `core/workflow_catalog.py`
   - `core/workflow_capabilities.py`
   - `runtime/cli.py`
   - `runtime/loader.py`
   - `core/context.py`
   - `core/stores/protocols.py`
   - `stdlib/_selected_workflow.py`
   - `stdlib/company.py`
   - `stdlib/evaluation.py`
   - `stdlib/portfolio.py`
4. Tests and docs that still enforce soon-to-be-removed surfaces
   - `tests/strictness/test_no_compat.py`
   - `tests/runtime/test_package_cli.py`
   - `tests/runtime/test_workflow_reference_resolution.py`
   - `tests/runtime/test_workflow_integration_parity.py`
   - `tests/runtime/test_compatibility_runtime.py`
   - `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
   - `tests/unit/test_stdlib_and_extensions.py`
   - `tests/test_architecture_baseline_docs.py`
   - `docs/architecture.md`
   - `docs/authoring.md`
   - active `docs/workflows/*.md`
   - `Workflow_Instructions.md`

### Non-obvious proof risks found during audit

1. `tests/strictness/test_no_compat.py` currently imports `workflow` and `workflow.primitives`.
   - The strictness suite must be rewritten before or alongside package deletion, otherwise the intended deletion becomes an immediate test failure instead of a guarded invariant.
2. `ResolvedWorkflow.package` has active callers outside loader-only tests.
   - Current consumers exist in `stdlib/` and multiple runtime suites, so this is broader than a local loader rename.
3. Active docs baseline drift exists around `cleanup.md`.
   - The active docs tests still treat root `cleanup.md` as maintained, but the file is absent in this checkout while `cleanup3.md` exists.
   - The docs cleanup/proof slice must leave the baseline aligned to one active working-tree note surface instead of ignoring the mismatch and discovering it at full-suite time.

## Implementation Milestones

### Milestone 1: Retry feedback specificity and public primitive exports

- Update `core/providers/retries.py` exactly as requested:
  - replace the generic `invalid_payload` summary branch with the route-aware / detail-aware logic
  - extend the retry action list with `question` and `blocked` / `failed` repair guidance
- Add route-specific and generic fallback tests in `tests/unit/test_provider_retries.py`
- Expose `Event`, `Outcome`, `Checkpoint`, `ResolvedArtifacts`, and `ChildWorkflowResult` from `autoloop.simple`
  - use the same installed-package / repo-root fallback import style already present in `autoloop/simple.py`
- Re-export the same names from `autoloop/__init__.py`
- Update public API tests to pin identity and presence on both surfaces

### Milestone 2: Remove the `workflow` package and finish runtime naming cleanup

- Port active imports away from `workflow` / `workflow.primitives`
  - public-facing imports move to `autoloop` or `autoloop.simple`
  - internal tests/helpers move to `core.primitives`, `core.artifacts`, and `core.context`
- Delete:
  - `workflow/__init__.py`
  - `workflow/primitives.py`
  - the `workflow/` package directory
- Remove `("workflow", "Workflow")` from both supported-base checks in `core/validation.py`
- Rename `legacy_workflow_path` to `workflow_py_path` across:
  - `WorkflowCatalogEntry`
  - `WorkflowCapabilityEntry`
  - catalog/capability payload builders
  - runtime CLI JSON payloads
  - related tests and assertions
- Rename `_load_legacy_parameter_type` to `_load_parameters_from_params_py`
  - rename local variables at call sites to match the new meaning
- Rename `is_legacy_run_key` to `is_run_key_bound_to_slot`
  - keep behavior unchanged
  - replace imports and call sites in `core/context.py` and `core/stores/protocols.py`
  - use the requested docstring
- Delete `ResolvedWorkflow.package` and replace all uses with `resolved.reference`

### Milestone 3: Strictness, docs, and proof

- Rewrite `tests/strictness/test_no_compat.py` so it no longer imports the deleted package
  - assert `repo_root / "workflow"` does not exist
  - forbid `from workflow`, `import workflow`, and `workflow.primitives` through regex/path scanning
  - add the requested guard for `_install_simple_workflow_step_handler`
  - extend forbidden symbol coverage with the exact tokens from the request
- Update runtime, CLI, loader, and stdlib-facing tests for:
  - `workflow_py_path`
  - removed `ResolvedWorkflow.package`
  - public primitive exports on `autoloop` and `autoloop.simple`
- Update active docs/examples so they only import from `autoloop` / `autoloop.simple`
- Align the active docs baseline to the real maintained working-tree note surface
  - either restore/update `cleanup.md` if it is still authoritative
  - or change the baseline/tests/docs consistently if `cleanup3.md` is the intended active note
  - do not leave both the baseline and working-tree note ownership ambiguous
- Run the targeted tests from the request, then full `pytest`

## Interface and Contract Updates

### Public authoring/runtime surface after cleanup

Supported public imports:

- `from autoloop import ...`
- `from autoloop.simple import ...`

Public exports to preserve:

- `AfterHookResult`
- `Json`
- `Md`
- `Prompt`
- `Raw`
- `Route`
- `RouteInfo`
- `StrictWorkflow`
- `Text`
- `Workflow`
- `WorkflowStep`
- `chain`
- `review_step`
- `step`
- `system_step`
- `workflow_step`

Public exports to add on both surfaces:

- `Event`
- `Outcome`
- `Checkpoint`
- `ResolvedArtifacts`
- `ChildWorkflowResult`

### Runtime/provider feedback contract

For `_provider_retry_kind == "invalid_payload"`:

- if `_failure_context["error"]` is present, emit it
- if `_failure_context["route"]` is also present, include the selected route
- if no specific error is present, keep the generic invalid-payload fallback

### Intentional compatibility breaks

- `workflow/` no longer exists
- `ResolvedWorkflow.package` no longer exists
- JSON payloads no longer expose `legacy_workflow_path`
- active source/docs must not import `workflow` or `workflow.primitives`
- no compatibility alias should remain for the removed names above

## Regression Controls

### Invariants that must remain true

- `workflow_package` remains a valid authoring-shape value
- parameter loading precedence remains class -> module -> package export -> `params.py` -> none
- run-key normalization behavior stays unchanged after the helper rename
- `WorkflowStep` execution behavior is unchanged; only an anti-regression guard is added
- ordinary control-schema invalid payload failures still keep the generic retry fallback when no route-specific error detail exists

### Validation strategy

Required targeted tests from the request:

- `pytest tests/unit/test_provider_retries.py`
- `pytest tests/unit/test_simple_surface.py`
- `pytest tests/strictness/test_no_compat.py`
- `pytest tests/runtime/test_package_cli.py`
- `pytest tests/runtime/test_workflow_reference_resolution.py`

Additional focused proof likely needed because the audited callers are outside the required list:

- `pytest tests/unit/test_primitives_and_stores.py`
- `pytest tests/unit/test_stdlib_and_extensions.py`
- `pytest tests/runtime/test_compatibility_runtime.py`
- `pytest tests/runtime/test_workflow_integration_parity.py`
- `pytest tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- `pytest tests/test_architecture_baseline_docs.py`

Final proof:

- `pytest`

## Risk Register

- `R1`: deleting `workflow/` before all imports are ported will break strictness/runtime/unit suites immediately.
  - Control: port callers first, then delete the package, then run the targeted suites that previously imported it.
- `R2`: `legacy_workflow_path` may be renamed in some serializers but not all.
  - Control: update catalog entry types, capability payload builders, CLI payloads, and assertion fixtures in one slice.
- `R3`: `ResolvedWorkflow.package` removal can miss non-loader callers.
  - Control: use repo-wide search hits as the authoritative caller list; update `stdlib/` and runtime suites in the same milestone.
- `R4`: active docs proof can fail for reasons unrelated to the requested import cleanup because the baseline still expects `cleanup.md`.
  - Control: make working-tree note ownership explicit during the docs slice instead of deferring the mismatch to full-suite proof.

## Rollback Guidance

- If retry feedback changes break provider tests unexpectedly, revert only the retry helper and its dedicated tests; do not roll back naming/deletion work.
- If `workflow/` deletion exposes hidden callers, temporarily revert only the directory deletion while keeping the import-port patch available as the reapply set; do not reintroduce a shim as a permanent fix.
- If docs proof fails on working-tree note ownership, revert only the docs-baseline alignment and re-land it with one clear authoritative note path.
