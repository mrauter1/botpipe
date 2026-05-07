# Implementation Notes

- Task ID: revised-sdk-implementation-spec-1-scope-implemen-1e1a7513
- Pair: implement
- Phase ID: sdk-retention-and-safe-cleanup
- Phase Directory Key: sdk-retention-and-safe-cleanup
- Phase Title: SDK Retention And Safe Cleanup
- Scope: phase-local producer artifact

## Files changed
- `autoloop/sdk.py`
- `autoloop/core/engine.py`
- `autoloop/core/operations.py`
- `tests/unit/test_sdk_facade.py`

## Symbols touched
- `Autoloop.__init__`, `Autoloop.run`, `Autoloop.step`, `Autoloop.cleanup`
- `SDKExecutionError`, `RetentionInfo`, `CleanupResult`, `ArtifactMap`, `WorkflowResult`
- `_write_sdk_task_sentinel`, `_safe_delete_sdk_task_dir`, `_collect_declared_write_artifacts`
- `_promote_declared_write`, `_apply_retention`, `_result_artifact_map_from_declared_writes`
- `_runtime_equivalent_artifact_context`, `_sdk_tasks_root`, `_default_routes_for_step`
- `Engine._resolve_prompt`
- `autoloop.core.operations._resolve_prompt`

## Checklist mapping
- Plan M2: completed
  Added retention plumbing, sentinel creation, safe deletion, declared-write collection/promotion, and conservative cleanup.
- Plan M3: partially completed
  Added runtime prompt rendering for bare `input.*` placeholders and preserved strict-step route-metadata compatibility while keeping spec defaults for route-less strict steps.
- Plan M4: partially completed
  Extended `tests/unit/test_sdk_facade.py` for retention, cleanup, scratch deletion/retention, and runtime prompt rendering. Helper entrypoints remain for a later phase.

## Assumptions
- Declared-write retention can reconstruct a runtime-equivalent artifact-resolution context from `RunExecution`, persisted params/input, request paths, and checkpoint session snapshots without changing runner internals.
- Cleanup should skip any sentinel-marked task whose completion status cannot be proven from `run.json`; this is safer than trying to infer success from directory shape alone.

## Preserved invariants
- SDK execution remains a thin wrapper over `execute_workflow_package(...)`.
- Retention never deletes workspace files outside the current SDK task directory.
- `llm(...)` and `classify(...)` remain outside SDK task retention scope in this slice.
- Artifact-path `ctx.*` rejection remains unchanged; only prompt rendering now adds bare `input.*` replacement.

## Intended behavior changes
- Successful SDK `run(...)` and `step(...)` now apply default retention: promote task-local declared writes, delete sentinel-marked task scratch, and return `WorkflowResult.retention`.
- Failed runs, unhandled input pauses, and too-many-pauses now keep task scratch by default and attach populated retention metadata to returned/raised partial results.
- `cleanup(...)` now removes only validated SDK task directories and supports conservative dry-run reporting.

## Known non-changes
- No workspace-file deletion policy was added beyond task-scratch removal.
- No retention/cleanup behavior was added to operation replay folders from `llm(...)` or `classify(...)`.
- No SDK helper constructors (`prompt_step`, `produce_verify_step`, `python_step`, `workflow_step`) were added in this phase.

## Validation performed
- `./.venv/bin/python -m pytest -q tests/unit/test_sdk_facade.py`
- `./.venv/bin/python -m pytest -q tests/unit/test_simple_surface.py -k 'input_message_prompt_binding or ctx_input_message_prompt_binding'`
- `python3 -m py_compile autoloop/sdk.py autoloop/core/engine.py autoloop/core/operations.py tests/unit/test_sdk_facade.py`

## Deduplication / centralization
- Centralized public artifact retention in `_apply_retention(...)` so successful returns and partial-result exceptions share one promotion/deletion path.
- Reused a single runtime-equivalent artifact-context builder for declared-write resolution instead of duplicating placeholder logic in the SDK.
