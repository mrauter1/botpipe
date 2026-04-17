# Implementation Notes

- Task ID: you-are-a-principal-software-architect-and-imple-5867bc5e
- Pair: implement
- Phase ID: autoloop-v1-parity-split
- Phase Directory Key: autoloop-v1-parity-split
- Phase Title: Replace The Support Mini-Runtime With Workflow-Owned Parity Modules
- Scope: phase-local producer artifact

## Files Changed

- `autoloop_v3/workflows/autoloop_v1_conventions.py`
- `autoloop_v3/workflows/autoloop_v1_parity.py`
- `autoloop_v3/workflows/__init__.py`
- `autoloop_v3/workflows/autoloop_v1_support.py` (deleted)
- `autoloop_v1.py`
- `Ralph_loop.py`
- `autoloop_v3/tests/runtime/test_compatibility_runtime.py`
- `autoloop_v3/tests/runtime/test_workflow_integration_parity.py`
- `autoloop_v3/README.md`
- `autoloop_v3/MIGRATION.md`
- `autoloop_v3/docs/architecture.md`
- `autoloop_v3/docs/authoring.md`
- `autoloop_v3/docs/compatibility.md`
- `autoloop_v3/docs/parity-matrix.md`
- `autoloop_v3/docs/risk-register.md`
- `.autoloop/tasks/you-are-a-principal-software-architect-and-imple-5867bc5e/decisions.txt`

## Symbols Touched

- `phase_dir_key(...)`
- `autoloop_v1_session_path(...)`
- `run_autoloop_v1(...)`
- `_AutoloopV1ParityObserver`
- `ensure_autoloop_v1_workspace(...)`
- `create_autoloop_v1_run(...)`
- `open_existing_autoloop_v1_run(...)`
- `parse_phase_ids(...)`
- `AutoloopV1.on_plan(...)`
- `RalphLoop.on_plan_action(...)`
- `RalphLoop.on_execute(...)`

## Checklist Mapping

- Plan milestone 3: completed by deleting `autoloop_v1_support.py`, adding parity/conventions modules, and migrating `autoloop_v1.py` in the same slice.
- Plan milestone 4: completed by fixing `Ralph_loop.py` strictness and direct-success `goal_met` handling.
- Plan milestone 5: completed for the required phase-adjacent docs/tests touched by this slice.

## Assumptions

- Resume-time clarification cycle/attempt can be recovered from the persisted raw phase log because the paused `question` entry is always written before resume.
- `autoloop_v1.py` is the only workflow that needs exact `phase_dir_key(...)` and legacy session-path rules today, so a tiny workflow-owned conventions module is the right shared scope.

## Preserved Invariants

- Engine/runtime remain Autoloop-agnostic and compatibility-free.
- Sessions remain explicit and direct-lookup only.
- `PairStep` and `LLMStep` handlers remain optional; `SystemStep` handlers remain required.
- Legacy `plan.json`, `sessions/phases/{phase}.json`, raw log, decisions, and status behaviors remain workflow-owned.

## Intended Behavior Changes

- Parity logging now comes from the generic observer seam instead of a provider wrapper plus engine subclass.
- `autoloop_v1.py` now states phase artifact templates directly and owns phase-plan parsing inline.
- `Ralph_loop.py` now leaves `goal_met=True` on both success paths.

## Known Non-Changes

- No generic workspace hook/plugin system was introduced.
- No Autoloop-specific logic was added to `workflow.engine` or `runtime.runner`.
- Session payload JSON ownership remains in `runtime.stores.filesystem`; parity only chooses when to call those helpers.

## Expected Side Effects

- Events/raw logs are emitted during execution from observer callbacks instead of after-the-fact wrapper/subclass hooks, but the persisted parity outputs remain the same.
- Docs now describe the split parity/conventions modules and the minimal generic observer seam.

## Validation Performed

- `pytest -q autoloop_v3/tests/runtime/test_compatibility_runtime.py::test_workspace_workflows_compile_through_the_strict_loader_surface autoloop_v3/tests/runtime/test_compatibility_runtime.py::test_autoloop_v1_source_inlines_phase_parsing_and_explicit_artifact_templates autoloop_v3/tests/runtime/test_compatibility_runtime.py::test_autoloop_v1_parity_modules_delegate_session_payload_writes_to_runtime_store_helpers autoloop_v3/tests/runtime/test_compatibility_runtime.py::test_filesystem_session_store_supports_custom_path_resolver`
- `pytest -q autoloop_v3/tests/runtime/test_workflow_integration_parity.py`
- `pytest -q autoloop_v3/tests/contract/test_engine_contracts.py`
- `pytest -q autoloop_v3/tests/test_architecture_baseline_docs.py autoloop_v3/tests/runtime/test_compatibility_runtime.py autoloop_v3/tests/runtime/test_workflow_integration_parity.py autoloop_v3/tests/contract/test_engine_contracts.py`
- `pytest -q autoloop_v3/tests`
- `pytest -q` (repo root; in progress when this note was first drafted, result captured in final turn report)

## Deduplication / Centralization Decisions

- Centralized exact legacy path rules in `autoloop_v1_conventions.py` instead of duplicating them across the workflow and harness.
- Centralized all parity interpretation in one observer-driven harness instead of splitting it between provider and engine extensions.
- Kept workflow semantics local by inlining `parse_phase_ids(...)` and explicit `Artifact(...)` templates directly in `autoloop_v1.py`.
