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
  `OperationRuntime.provider_policy_resolver`
- Checklist mapping:
  Plan milestone 2 completed for the approved phase scope.
  Added the four primitive modules and the AST-aware core/runtime boundary test.
  Updated runtime `ProviderPolicyResolver` and core typing to use the new protocol.
  Deferred route, step, and workflow adapter bodies beyond ArtifactId conversions.
- Assumptions:
  Import-statement strictness is the enforceable boundary for this milestone, so `importlib` lookup is acceptable as an interim compatibility bridge.
  Private Context-backed `RunPaths` and `RunIdentity` are sufficient initial integration until the later ExecutionFrame phase.
- Preserved invariants:
  No public root exports changed.
  No `botlane.core.__all__` changes.
  No SDK/simple signature changes.
  No runtime execution flow changes beyond provider-policy resolver lookup plumbing.
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
- Deduplication / centralization:
  Centralized ArtifactId conversion logic in `botlane/core/plan_adapters.py`.
  Centralized runtime-loader lookup in `workflow_capabilities.py` and default provider-policy resolver lookup in `engine.py` to remove direct core runtime imports without broad refactors.
