# Implementation Notes

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: implement
- Phase ID: consumer-migration-and-package-cleanup
- Phase Directory Key: consumer-migration-and-package-cleanup
- Phase Title: Consumer Migration
- Scope: phase-local producer artifact

## Files Changed

- `autoloop_optimizer/__init__.py`
- `autoloop_optimizer/parameters.py`
- `core/descriptors.py`
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
- `effective_parameters_model`
- workflow-capability payload `writes` / `routes` / `required_writes`
- optimizer helper import paths
- stdlib public surface pruning
- topology-hash / static-graph JSON normalization
- provider artifact lookup normalization for raw artifact references
- CLI package execution reference preservation
- `capture_decomposition_context` blocked-route contract

## Checklist Mapping

- Public/test/doc consumer rename to `Params`, `writes`, `required_writes`: advanced; updated runtime/package/unit consumer assertions and authoring docs in this phase slice
- Workflow package import/fallback cleanup: advanced; package CLI/runtime flows now preserve package `Params` across execution
- Optimizer-vs-stdlib separation: advanced; shared parameter bundles moved to `autoloop_optimizer.parameters`, stdlib re-exports removed, consumer docs/tests/workflows retargeted
- Reduced stdlib surface and consumer migration to `autoloop_optimizer`: advanced; remaining legacy compatibility tests outside this slice still need follow-up cleanup

## Preserved Invariants

- Repo-root runtime/compiler package remains the active implementation target.
- Legacy reader normalization for persisted payloads was not broadened beyond already-in-flight runtime work.
- Workflow package authoring continues to compile through the active runtime loader rather than new sidecar loaders.
- Resume/answer still resolve by workflow name and existing run metadata; only fresh-run execution changed to preserve package reference context.

## Intended Behavior Changes

- Workflow packages now export `Params` instead of `Parameters`.
- Capability inspection now emits canonical step kinds, `writes`, and `routes` metadata.
- Workflow-package/docs/test consumers are being migrated off optimizer helpers re-exported from `stdlib`.
- CLI `run` keeps manifest-package `Params` available during execution by passing the original workflow reference through the runner.
- `workflow_package_to_composable_building_blocks.capture_decomposition_context` can legally route `blocked -> PAUSE`.

## Known Non-Changes

- Low-level compatibility/internal tests still contain substantial legacy terminology and were not fully migrated in this turn.
- Internal strict-step scaffolding (`LLMStep`, `PairStep`, `SystemStep`, `RouteInfo`) was not removed in this phase.
- Capability snapshot step payloads still use the existing `has_expected_output_schema` / `typed_output_schema` JSON field names for out-of-phase consumers.

## Validation Performed

- `./.venv/bin/python -m pytest tests/runtime/test_workflow_builder_package.py::test_workflow_builder_package_runs_and_generates_a_compilable_package -q`
  - passed
- `./.venv/bin/python -m pytest tests/runtime/test_workflow_package_to_composable_building_blocks.py::test_workflow_package_to_composable_building_blocks_routes_to_blocked_for_unreadable_evidence_paths tests/runtime/test_workflow_reference_resolution.py::test_simple_declaration_workflow_is_discoverable_by_path_module_name_and_capability_inspection tests/runtime/test_workflow_reference_resolution.py::test_parameter_resolution_follows_class_module_package_legacy_then_none tests/runtime/test_package_cli.py::test_cli_workflows_show_reports_parameters_and_aliases tests/runtime/test_package_cli.py::test_cli_serializes_typed_workflow_parameters_as_json_safe_values tests/runtime/test_package_cli.py::test_cli_rejects_invalid_or_unsupported_workflow_params -q`
  - 6 passed
- `./.venv/bin/python -m pytest tests/unit/test_stdlib_and_extensions.py -k 'parameter_model_bundles_preserve_shared_task_and_selected_workflow_normalization or portfolio_helpers_keep_catalog_snapshot_lightweight_and_capability_snapshot_rich or adaptation_helpers_snapshot_one_selected_workflow_without_importing_unrelated_packages or authoring_doc_describes_additive_evaluation_helper_boundary or authoring_doc_describes_additive_refinement_surface_helper_boundary or authoring_doc_describes_additive_decomposition_surface_helper_boundary or authoring_doc_describes_additive_portfolio_health_snapshot_helper_boundary or authoring_doc_describes_additive_company_operation_snapshot_helper_boundary or authoring_doc_describes_additive_diagnostics_snapshot_helper_boundary or route_helpers_return_explicit_normalized_bundles' -q`
  - 10 passed, 85 deselected
- `./.venv/bin/python -m pytest tests/runtime/test_workflow_builder_package.py tests/runtime/test_task_to_candidate_workflow_set.py tests/runtime/test_task_to_workflow_strategy.py tests/runtime/test_workflow_to_eval_suite.py tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/runtime/test_workflow_run_traces_to_optimization_candidates.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/runtime/test_workflow_reference_resolution.py tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py tests/runtime/test_package_cli.py -q`
  - 294 passed; warnings only from existing Pydantic `schema` field-name collisions in optimization workflow contracts

## Deduplication / Centralization

- Optimizer/application helpers were moved toward `autoloop_optimizer` as the single canonical home.
- Topology/static-graph JSON object normalization was centralized in compiler/static-graph helpers instead of repeated callsite workarounds.
- Package-level `Params` handling now centralizes on the original workflow reference path instead of duplicating class-only parameter discovery during CLI execution.
