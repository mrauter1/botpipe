# Implementation Notes

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: implement
- Phase ID: execution-services-and-collaborators
- Phase Directory Key: execution-services-and-collaborators
- Phase Title: Execution Services
- Scope: phase-local producer artifact

## Files Changed

- `botlane/core/execution_services.py`
- `botlane/core/engine.py`
- `botlane/core/engine_collaborators.py`
- `botlane/core/plan_adapters.py`
- `tests/contract/engine/test_execution_services.py`

## Symbols Touched

- `ExecutionServices`, `ArtifactService`, `RouteService`, `HookService`, `StateService`
- `Engine.execution_services`, `_EngineArtifactService`, `_EngineRouteService`, `_EngineStateService`
- `ArtifactGuard`, `RouteFinalizer`
- `ProviderContractBuilder.readable_refs_from_turn`, `_readable_ref_from_turn`, `_fan_in_workspace_path`
- `step_plan_from_compiled_step`, `_step_header_from_compiled_step`, `_step_source_refs`, `_read_ref_from_compiled`, `_require_ref_from_compiled`

## Checklist Mapping

- ExecutionServices shell: completed via `botlane/core/execution_services.py`
- ArtifactGuard migration: completed via service-backed delegation
- RouteFinalizer migration: completed via service-backed route/artifact/hook/state adapters
- Updated contract coverage: completed via `tests/contract/engine/test_execution_services.py`
- Later collaborator migrations (`HookRunner`, `StepDispatcher`, `BranchGroupRuntime`, others): deferred to later phases

## Assumptions

- Internal service adapters may temporarily delegate to `Engine` private helpers as a bridge, provided ownership is narrowed and TODO-scoped.
- Phase-local parity fixes are allowed when the new service seam exposes regressions in already-migrated provider-turn / step-plan paths.

## Preserved Invariants

- No public API or export changes
- `RouteFinalizationResult` / engine loop behavior unchanged
- Branch manifest/event shapes unchanged
- Provider transport boundary remains `RenderedProviderTurn` / `ProviderTurnResult`
- Strictness scan remains narrow; no new allowlist entries were added for this phase

## Intended Behavior Changes

- Internal only: `ArtifactGuard` and `RouteFinalizer` no longer depend on `Engine` directly; they depend on narrow execution-service seams.

## Known Non-Changes

- `StepDispatcher`, `HookRunner`, `BranchGroupRuntime`, `CheckpointManager`, `SessionRuntime`, and `StateRuntime` still own their existing `Engine` coupling.
- No engine rewrite and no public route/action API changes.

## Expected Side Effects

- `Engine` now exposes an internal `execution_services` bundle for collaborator wiring.
- Provider-turn plan adaptation preserves fan-in helper semantics without treating literal `_branch_groups/...` workflow reads as fan-in-only helpers.

## Deduplication / Centralization

- Centralized migrated collaborator dependencies in `ExecutionServices` instead of adding new collaborator-specific engine reach-throughs.
- Centralized fan-in helper resolution for typed provider-turn refs in `ProviderContractBuilder`.

## Validation Performed

- `.venv/bin/python -m pytest tests/contract/engine/test_execution_services.py tests/contract/engine/test_artifacts.py tests/contract/engine/test_routes.py tests/contract/test_provider_turn_plan_adapter.py`
- `.venv/bin/python -m pytest tests/contract/engine tests/contract/test_branch_group_runtime.py`
- `.venv/bin/python -m pytest tests/unit/test_simple_surface.py tests/unit/test_sdk_facade.py tests/strictness/test_no_compat.py`

## Out-of-Phase Justification

- `botlane/core/plan_adapters.py` received two parity fixes while validating this phase:
  - producer turns keep `expected_output_schema=None`
  - fan-in helpers are inferred from authored helper refs, while literal `_branch_groups/...` reads remain plain workspace reads
- These changes were required to preserve existing runtime behavior after the collaborator seam continued exercising the plan-based provider contract path.
