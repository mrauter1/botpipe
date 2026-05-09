# Implementation Notes

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: implement
- Phase ID: boundary-primitives-and-strictness
- Phase Directory Key: boundary-primitives-and-strictness
- Phase Title: Boundary Primitives
- Scope: phase-local producer artifact
- Files changed:
  `botlane/core/identifiers.py`
  `botlane/core/run_paths.py`
  `botlane/core/provider_policy_resolution.py`
  `botlane/core/plan_adapters.py`
  `botlane/core/context.py`
  `botlane/core/engine.py`
  `botlane/core/operations.py`
  `botlane/core/workflow_capabilities.py`
  `botlane/runtime/provider_policy_resolver.py`
  `tests/unit/test_artifact_ids.py`
  `tests/unit/test_run_paths.py`
  `tests/runtime/test_provider_policy_core_protocol.py`
  `tests/strictness/test_core_runtime_boundary.py`
- Symbols touched:
  `ArtifactId`
  `RunPaths`
  `RunIdentity`
  `ProviderPolicyResolverProtocol`
  `artifact_id_from_compiled_artifact`
  `artifact_id_from_inventory_record`
  `artifact_id_for_reference`
  `Context._run_paths`
  `Context._run_identity`
  `Engine.provider_policy_resolver`
  `_DefaultProviderPolicyResolver`
  `OperationRuntime.provider_policy_resolver`
  `inspect_workflow_reference`
  `_resolve_reference`
  `_resolved_from_catalog_entry`
  `_resolve_workflow_class_reference`
- Checklist mapping:
  Plan milestone 2 completed for the approved phase scope.
  Added the four primitive modules and the AST-aware core/runtime boundary test.
  Updated runtime `ProviderPolicyResolver` and core typing to use the new protocol.
  Deferred route, step, and workflow adapter bodies beyond ArtifactId conversions.
- Assumptions:
  Private Context-backed `RunPaths` and `RunIdentity` are sufficient initial integration until the later ExecutionFrame phase.
- Preserved invariants:
  No public root exports changed.
  No `botlane.core.__all__` changes.
  No SDK/simple signature changes.
  No `botlane/core` runtime imports remain outside `TYPE_CHECKING`.
- Intended behavior changes:
  None for public users; this is internal typing, identity, and strictness coverage only.
- Known non-changes:
  `plan_adapters.py` does not yet implement route/step/workflow conversions.
  Engine still consumes `CompiledWorkflow`.
  No route-contract, workflow-plan, or execution-frame work landed in this phase.
- Expected side effects:
  Core/runtime boundary enforcement now fails on import-statement regressions under `botlane/core`.
  Context instances now carry private run identity/path objects for later phases.
- Validation performed:
  `.venv/bin/python -m pytest tests/unit/test_artifact_ids.py`
  `.venv/bin/python -m pytest tests/unit/test_run_paths.py`
  `.venv/bin/python -m pytest tests/runtime/test_provider_policy_core_protocol.py`
  `.venv/bin/python -m pytest tests/strictness/test_core_runtime_boundary.py`
  `.venv/bin/python -m pytest tests/unit/test_simple_surface.py`
  `.venv/bin/python -m pytest tests/unit/test_sdk_facade.py`
  `.venv/bin/python -m pytest tests/strictness/test_no_compat.py`
  `.venv/bin/python -m pytest tests/runtime/test_workflow_reference_resolution.py`
  `.venv/bin/python -m pytest tests/unit/optimizer/test_selected_workflow_helpers.py`
  `.venv/bin/python -m pytest tests/unit/test_artifact_ids.py tests/unit/test_run_paths.py tests/runtime/test_provider_policy_core_protocol.py tests/strictness/test_core_runtime_boundary.py tests/unit/test_simple_surface.py tests/unit/test_sdk_facade.py tests/strictness/test_no_compat.py tests/runtime/test_workflow_reference_resolution.py tests/unit/optimizer/test_selected_workflow_helpers.py`
- Deduplication / centralization:
  Centralized ArtifactId conversion logic in `botlane/core/plan_adapters.py`.
  Centralized the core-only fallback provider-policy path in `engine.py` and the catalog-aware workflow capability resolution path in `workflow_capabilities.py` so the boundary fix does not depend on `botlane.runtime`.
