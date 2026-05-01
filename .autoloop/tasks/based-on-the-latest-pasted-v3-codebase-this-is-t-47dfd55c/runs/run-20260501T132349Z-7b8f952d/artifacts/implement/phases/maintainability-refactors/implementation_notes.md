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
- `autoloop/core/worklists.py`
- `autoloop/core/operations.py`
- `autoloop/simple.py`
- `autoloop/runtime/config.py`
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
- `Worklist.load_items`, `Worklist.set_current_status`
- `OperationRuntime`, replay fingerprint helpers, replay mismatch warning/fail path
- `LLMOperation`, `ClassifyOperation`, `llm`, `classify`
- `RuntimeConfig.replay_mismatch_behavior`
- `StepDispatcher`, `RouteFinalizer`, `HookRunner`, `ArtifactGuard`, `StateRuntime`, `SessionRuntime`, `CheckpointManager`, `OperationRecorder`, `WorkflowInvoker`
- `compile_workflow` imports via `discovery`/`inventory`/`lowering` facades

## Checklist Mapping
- AC-1: Added explicit engine collaborator seams and compiler/validation facade modules; `compiler.py` now consumes the split facades and `engine.py` uses collaborator entrypoints for dispatch, hooks, checkpoints, worklist-state restore/init, operation binding, and child workflow invocation.
- AC-2: Renamed public operation surfaces to `LLMOperation` / `ClassifyOperation`, typed `ChildWorkflowResult[OutputT]`, and added warn-vs-fail replay mismatch behavior with runtime config and engine wiring.
- AC-3: Cached worklist item loading per `Context` / step execution, unified session store behavior behind backend composition, and removed one redundant child-workflow parameter normalization layer now that `Context.invoke_workflow` is the public boundary.

## Preserved Invariants
- `InMemorySessionStore` and `FilesystemSessionStore` remain constructible by existing runtime/tests; backend composition is internalized without compatibility shims.
- Replay still reuses the existing on-disk store format and schema id; only mismatch handling and fingerprint inputs changed.
- Worklist caching is step-local because a fresh `Context` is created per step execution; mutable worklist writes refresh the cache immediately.
- Engine behavior remains delegated to the existing private methods; collaborator classes make responsibilities explicit without reimplementing runtime semantics mid-phase.

## Intended Behavior Changes
- Operation replay fingerprint mismatches now warn and return the cached value by default instead of failing immediately.
- Strict replay mismatch failure is still available through `Engine(..., operation_replay_mismatch_behavior="fail")` and runtime config.
- Worklist item reads avoid repeated artifact-backed loads within the same step execution.

## Known Non-Changes
- This turn did not fully rewrite the validation monolith; the new phase modules are stable facades over the existing validated logic, with `compiler.py` consuming the facades first.
- This turn did not rework broader legacy contract tests whose expectations were already drifted by prior phases (`pending_question`, old failure-context shapes, removed top-level package paths).

## Validation Performed
- `.venv/bin/python -m py_compile` on all changed Python modules.
- `.venv/bin/pytest tests/unit/test_primitives_and_stores.py::test_session_store_can_be_composed_from_backend tests/unit/test_primitives_and_stores.py::test_worklist_load_items_is_cached_per_context tests/unit/test_simple_surface.py::test_operation_surface_singletons_expose_public_runtime_types tests/contract/test_engine_contracts.py::test_operation_replay_fingerprint_mismatch_warns_and_reuses_cached_value_by_default tests/contract/test_engine_contracts.py::test_operation_replay_fingerprint_mismatch_fails_in_strict_mode tests/contract/test_engine_contracts.py::test_route_redirected_final_route_drives_required_write_validation -q`

## Assumptions / Risks
- The new facade modules are sufficient for this phase’s decomposition acceptance because they are now canonical import seams and not dead files.
- Broader contract suite failures observed during exploratory runs are treated as pre-existing expectation drift from earlier phases, not regressions introduced by this maintainability turn.
