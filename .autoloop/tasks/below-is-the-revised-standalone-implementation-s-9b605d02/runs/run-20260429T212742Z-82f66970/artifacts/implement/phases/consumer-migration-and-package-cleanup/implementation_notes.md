# Implementation Notes

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: implement
- Phase ID: consumer-migration-and-package-cleanup
- Phase Directory Key: consumer-migration-and-package-cleanup
- Phase Title: Consumer Migration
- Scope: phase-local producer artifact

## Files Changed

- `runtime/loader.py`
- `runtime/cli.py`
- `core/workflow_capabilities.py`
- `core/compiler.py`
- `core/engine.py`
- `runtime/static_graph.py`
- `stdlib/__init__.py`
- `stdlib/control.py`
- `stdlib/prompts.py`
- `stdlib/steps.py`
- `autoloop_optimizer/*.py`
- `workflows/*/params.py`
- `workflows/*/__init__.py`
- selected `workflows/*/workflow.py`
- selected `tests/runtime/*.py`
- `tests/unit/test_stdlib_and_extensions.py`
- `docs/authoring.md`
- `docs/architecture.md`
- `docs/workflows/*.md`

## Symbols Touched

- `Params` package resolution and validation
- workflow-capability payload `writes` / `routes` / `required_writes`
- optimizer helper import paths
- stdlib public surface pruning
- topology-hash / static-graph JSON normalization
- provider artifact lookup normalization for raw artifact references

## Checklist Mapping

- Public/test/doc consumer rename to `Params`, `writes`, `required_writes`: partial
- Workflow package import/fallback cleanup: partial
- Optimizer-vs-stdlib separation: partial
- Reduced stdlib surface and consumer migration to `autoloop_optimizer`: partial

## Preserved Invariants

- Repo-root runtime/compiler package remains the active implementation target.
- Legacy reader normalization for persisted payloads was not broadened beyond already-in-flight runtime work.
- Workflow package authoring continues to compile through the active runtime loader rather than new sidecar loaders.

## Intended Behavior Changes

- Workflow packages now export `Params` instead of `Parameters`.
- Capability inspection now emits canonical step kinds, `writes`, and `routes` metadata.
- Workflow-package/docs/test consumers are being migrated off optimizer helpers re-exported from `stdlib`.

## Known Non-Changes

- Low-level compatibility/internal tests still contain substantial legacy terminology and were not fully migrated in this turn.
- Internal strict-step scaffolding (`LLMStep`, `PairStep`, `SystemStep`, `RouteInfo`) was not removed in this phase.

## Validation Performed

- `./.venv/bin/python -m pytest tests/runtime/test_workflow_builder_package.py::test_workflow_builder_package_compiles_with_explicit_control_contracts -q`
  - passed after compiler normalization fixes
- Focused runtime suite run:
  - `./.venv/bin/python -m pytest tests/runtime/test_workflow_builder_package.py tests/runtime/test_task_to_candidate_workflow_set.py tests/runtime/test_task_to_workflow_strategy.py tests/runtime/test_workflow_to_eval_suite.py tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/runtime/test_workflow_run_traces_to_optimization_candidates.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/runtime/test_workflow_reference_resolution.py tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py -q`
  - still failing broadly; main fixed blockers were topology/static-graph JSON serialization and raw artifact reference lookup in provider-contract assembly

## Deduplication / Centralization

- Optimizer/application helpers were moved toward `autoloop_optimizer` as the single canonical home.
- Topology/static-graph JSON object normalization was centralized in compiler/static-graph helpers instead of repeated callsite workarounds.
