# Implementation Notes

- Task ID: based-on-the-latest-pasted-v3-codebase-this-is-t-47dfd55c
- Pair: implement
- Phase ID: maintainability-refactors
- Phase Directory Key: maintainability-refactors
- Phase Title: Maintainability Refactors
- Scope: phase-local producer artifact

## Files Changed
- `autoloop/core/stores/session_store.py`
- `autoloop/core/stores/memory.py`
- `autoloop/core/stores/__init__.py`
- `autoloop/runtime/stores/filesystem.py`
- `autoloop/runtime/stores/__init__.py`
- `autoloop/core/context.py`
- `autoloop/core/mappings.py`
- `autoloop/core/worklists.py`
- `autoloop/core/operations.py`
- `autoloop/simple.py`
- `autoloop/runtime/config.py`
- `autoloop/runtime/loader.py`
- `autoloop/runtime/prompts.py`
- `autoloop/runtime/runner.py`
- `autoloop/core/engine_collaborators.py`
- `autoloop/core/discovery.py`
- `autoloop/core/inventory.py`
- `autoloop/core/lowering.py`
- `autoloop/core/topology.py`
- `autoloop/core/hook_validation.py`
- `autoloop/core/prompt_validation.py`
- `autoloop/core/state_validation.py`
- `autoloop/core/compiler.py`
- `autoloop/core/engine.py`
- `autoloop/stdlib/composition.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/unit/test_simple_surface.py`
- `tests/contract/test_engine_contracts.py`

## Symbols Touched
- `SessionStore`, `SessionBackend`, `InMemorySessionBackend`, `InMemorySessionStore`
- `FilesystemSessionBackend`, `FilesystemSessionStore`
- `ChildWorkflowResult[OutputT]`, `Context.invoke_workflow`
- `normalize_mapping(...)` ingress helpers
- `Worklist.load_items`, `Worklist.set_current_status`
- `OperationRuntime`, `provider_configuration(...)`, replay fingerprint helpers, replay mismatch warning/fail path
- `LLMOperation`, `ClassifyOperation`, `llm`, `classify`
- `RuntimeConfig.replay_mismatch_behavior`
- `StepDispatcher`, `RouteFinalizer`, `HookRunner`, `ArtifactGuard`, `StateRuntime`, `SessionRuntime`, `CheckpointManager`, `OperationRecorder`, `WorkflowInvoker`
- `WorkflowDefinition` discovery/lowering/topology helpers moved behind owned phase modules, with `validation.py` reduced to orchestration and re-exports

## Checklist Mapping
- AC-1: Kept the engine collaborator seams from turn 1 and completed the validation/compiler ownership split by moving workflow-definition, artifact-inventory, lowering, topology, hook-signature, and state/worklist validation logic out of `validation.py` into the requested modules.
- AC-2: Renamed public operation surfaces to `LLMOperation` / `ClassifyOperation`, typed `ChildWorkflowResult[OutputT]`, and tightened replay fingerprints to include resolved prompt-reference metadata plus concrete provider configuration while preserving warn-vs-fail mismatch behavior.
- AC-3: Cached worklist item loading per `Context` / step execution and centralized Mapping-to-dict normalization through `autoloop.core.mappings.normalize_mapping(...)` at the loader, context, workspace, runner, and filesystem-persistence boundaries.

## Preserved Invariants
- `InMemorySessionStore` and `FilesystemSessionStore` remain constructible by existing runtime/tests; backend composition is internalized without compatibility shims.
- Replay still reuses the existing on-disk store format and schema id; only mismatch handling and fingerprint inputs changed.
- Worklist caching is step-local because a fresh `Context` is created per step execution; mutable worklist writes refresh the cache immediately.
- Engine behavior remains delegated to the existing private methods; collaborator classes make responsibilities explicit without reimplementing runtime semantics mid-phase.
- Public/runtime mapping validation semantics are unchanged; ingress helpers copy mappings once, and downstream workflow-parameter validation still rejects unknown or invalid names where it did before.

## Intended Behavior Changes
- Operation replay fingerprint mismatches now warn and return the cached value by default instead of failing immediately.
- Strict replay mismatch failure is still available through `Engine(..., operation_replay_mismatch_behavior="fail")` and runtime config.
- Provider model/config drift now participates in operation replay mismatch detection even when the provider class stays the same.
- Worklist item reads avoid repeated artifact-backed loads within the same step execution.

## Known Non-Changes
- This turn did not rework broader legacy contract tests whose expectations were already drifted by prior phases (`pending_question`, old failure-context shapes, removed top-level package paths).

## Validation Performed
- `.venv/bin/python -m py_compile` on all changed Python modules.
- `.venv/bin/pytest tests/unit/test_primitives_and_stores.py::test_session_store_can_be_composed_from_backend tests/unit/test_primitives_and_stores.py::test_worklist_load_items_is_cached_per_context tests/unit/test_simple_surface.py::test_operation_surface_singletons_expose_public_runtime_types tests/contract/test_engine_contracts.py::test_operation_replay_fingerprint_mismatch_warns_and_reuses_cached_value_by_default tests/contract/test_engine_contracts.py::test_operation_replay_fingerprint_mismatch_fails_in_strict_mode tests/contract/test_engine_contracts.py::test_operation_replay_fingerprint_includes_provider_configuration tests/contract/test_engine_contracts.py::test_route_redirected_final_route_drives_required_write_validation -q`
- `.venv/bin/pytest tests/contract/test_engine_contracts.py::test_low_level_engine_requires_prompt_registry_for_relative_file_prompts tests/contract/test_engine_contracts.py::test_low_level_engine_resolves_relative_file_prompts_with_filesystem_registry tests/runtime/test_workspace_and_context.py::test_context_invoke_workflow_accepts_imported_main_workflow_classes_and_records_child_metadata tests/runtime/test_workspace_and_context.py::test_context_invoke_workflow_supports_typed_child_input_and_output tests/runtime/test_workspace_and_context.py::test_new_runs_validate_workflow_params_before_persisting_run_metadata -q`

## Assumptions / Risks
- Broader contract suite failures observed during exploratory runs are treated as pre-existing expectation drift from earlier phases, not regressions introduced by this maintainability turn.
- `prompt_validation.py` remains a small public helper surface because simple-step prompt placeholder inference is part of workflow discovery ownership; the authoritative implementation now lives outside `validation.py`.
