# Implementation Notes

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: implement
- Phase ID: canonical-type-hardening
- Phase Directory Key: canonical-type-hardening
- Phase Title: Canonical Type Hardening
- Scope: phase-local producer artifact

## Files changed

- `botlane/core/artifact_plan.py`
- `botlane/core/artifacts.py`
- `botlane/core/workflow_plan.py`
- `botlane/core/step_plans.py`
- `botlane/core/route_contracts.py`
- `botlane/core/reference_graph.py`
- `botlane/core/execution_services.py`
- `botlane/core/plan_adapters.py`
- `botlane/core/branch_groups/manifest.py`
- `tests/unit/test_artifact_ids.py`
- `tests/unit/test_step_plans.py`
- `tests/unit/test_workflow_plan_adapters.py`
- `tests/contract/test_branch_result_serialization.py`

## Symbols touched

- `ArtifactSpec`, `ArtifactKind`
- `WorkflowPlan.new_state`, `WorkflowPlan.public_artifacts`, `WorkflowPlan.artifacts_by_qualified_name`
- `StepSource`, `StepHeader.source`, `ProviderTurnKind`
- `ReferenceGraph.empty`
- `RouteDecision.pending_handoffs`
- `ExecutionServices` protocol surfaces
- `BranchManifest`, `build_branch_manifest`, `write_branch_group_evidence`, `render_branch_group_context`
- `workflow_plan_from_compiled`, `compiled_workflow_from_plan`, `step_plan_from_compiled_step`

## Checklist mapping

- Plan Phase 1 / canonical type hardening:
- Added canonical `artifact_plan.py`.
- Corrected `WorkflowPlan`, `StepHeader`, `StepSource`, `ReferenceGraph`, and `BranchManifest` shapes.
- Kept canonical plan/runtime types internal; no public export edits.
- Retargeted adapter tests to the new internal fields while preserving the compiled bridge for this phase.

## Assumptions

- Phase 1 can harden canonical dataclass shapes before Phase 2 deletes compiled compatibility objects.
- Adapter-based reconstruction may require explicit `_compiled_step` parity metadata once `StepHeader.original_step` is removed.

## Preserved invariants

- `botlane.__all__`, `botlane.core.__all__`, and `botlane.core.branch_groups.__all__` were not changed.
- `CompiledArtifact`, compiled workflow objects, and `plan_adapters.py` remain present for later atomic cutover work.
- Public artifact handle behavior in `artifacts.py` remains unchanged.
- Branch evidence schema remains `botlane.branch_results/v1`.

## Intended behavior changes

- Internal workflow plans now use `ArtifactId -> ArtifactSpec` inventory plus explicit public/qualified-name index maps.
- `StepHeader` now carries metadata-only `StepSource` instead of an authored-step field.
- `build_branch_manifest(...)` now returns typed `BranchManifest`.

## Known non-changes

- No compiler/runtime cutover in this phase.
- No compiled-object deletions in this phase.
- No branch-group export cleanup in this phase.
- No placeholder parser centralization changes in this phase beyond `ReferenceGraph` shape completion.

## Expected side effects

- Adapter round-trips now depend on parity metadata instead of `StepHeader.original_step`.
- Tests that asserted adapter-era header/artifact shapes were updated to assert canonical internal fields instead.

## Validation performed

- `.venv/bin/python -m pytest tests/unit/test_artifact_ids.py tests/unit/test_route_contracts.py tests/unit/test_placeholder_refs.py tests/unit/test_step_plans.py tests/unit/test_workflow_plan_adapters.py tests/contract/test_branch_result_serialization.py -q`
- `.venv/bin/python -m pytest tests/unit/test_public_surface.py tests/unit/test_sdk_facade.py tests/contract/engine/test_execution_services.py -q`

## Deduplication / centralization decisions

- Centralized canonical artifact metadata in `botlane/core/artifact_plan.py`.
- Kept `artifacts.py` as the artifact declaration/handle surface while using adapter helpers to bridge compiled artifacts into `ArtifactSpec`.
