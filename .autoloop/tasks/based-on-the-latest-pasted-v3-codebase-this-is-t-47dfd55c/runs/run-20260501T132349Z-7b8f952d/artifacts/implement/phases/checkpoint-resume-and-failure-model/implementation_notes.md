# Implementation Notes

- Task ID: based-on-the-latest-pasted-v3-codebase-this-is-t-47dfd55c
- Pair: implement
- Phase ID: checkpoint-resume-and-failure-model
- Phase Directory Key: checkpoint-resume-and-failure-model
- Phase Title: Checkpoint Resume And Failure Model
- Scope: phase-local producer artifact

## Files changed
- `core/errors.py`
- `core/context.py`
- `core/engine.py`
- `core/operations.py`
- `core/providers/retries.py`
- `runtime/runner.py`
- `runtime/workspace.py`
- `runtime/cli.py`
- `runtime/stores/filesystem.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_compatibility_runtime.py`
- `tests/runtime/test_package_cli.py`
- `tests/unit/test_provider_retries.py`
- `tests/unit/test_simple_surface.py`
- `decisions.txt`

## Symbols touched
- `FailureContext`, `StepExecutionError`, `ProviderExecutionError`
- `Context.step_state`, `Context.step_item_state`, `StateView`
- `Engine._resume_input_response`, `_save_checkpoint`, `_failure_context_for_exception`, `_ensure_retry_failure_context`, `_annotate_execution_error`
- `build_retry_feedback` failure-context readers
- `update_run_metadata`, `RunRecord.pending_input`

## Checklist mapping
- Pending input persistence and resume validation: done
- `ctx.input_response` resume path and consumed-input clearing: done
- Structured failure context and execution error surfaces: done
- Read-only runtime-owned step/step-item built-ins: done
- Focused regression coverage for resume/failure/state-view behavior: done

## Assumptions
- Legacy run-record readers may keep a derived `pending_question` convenience property while new metadata writes use only `pending_input`.
- Legacy checkpoint payloads with only `pending_question` are not safely resumable and should fail explicitly instead of guessing schema/typing.

## Preserved invariants
- Custom state and session mutations still persist on failure.
- Built-in route-state fields still update only on finalized route transitions.
- Checkpoint serialization for step state, item state, and sessions remains structurally unchanged.

## Intended behavior changes
- New checkpoint and run metadata writes stop persisting duplicate `pending_question`.
- Resume-time input validation failures now checkpoint structured failure context and keep the pending input open.
- `ctx.step_state` / `ctx.step_item_state` reject assignment to runtime-owned built-ins while allowing custom-field mutation.
- Non-provider hook/finalization/runtime-control failures now retain mutated checkpoint state and structured failure context without changing the original exception type.

## Known non-changes
- Legacy checkpoint files still load `pending_question` when present for compatibility reads.
- Runtime/history persistence still stores checkpoint failure context as JSON payloads, not typed Python objects.
- The broader CLI import-path issue in direct top-level test import was not changed in this phase.

## Expected side effects
- CLI `run` / `runs show` payloads now surface `pending_input` instead of `pending_question`.
- Provider retry and operation retry helpers now read structured retry metadata from public exception attributes.

## Validation performed
- `python3 -m py_compile core/errors.py core/context.py core/engine.py core/operations.py core/providers/retries.py runtime/runner.py runtime/workspace.py runtime/cli.py runtime/stores/filesystem.py tests/unit/test_provider_retries.py`
- `.venv/bin/python -m pytest -q tests/unit/test_provider_retries.py tests/unit/test_simple_surface.py::test_simple_context_suppresses_unmodeled_item_state_surfaces tests/unit/test_simple_surface.py::test_simple_context_exposes_modeled_item_state_surfaces tests/unit/test_simple_surface.py::test_simple_context_step_item_state_runtime_fields_are_read_only tests/contract/test_engine_contracts.py::test_after_hook_request_input_checkpoints_pending_input_and_resume_validates_input tests/contract/test_engine_contracts.py::test_resume_invalid_pending_input_preserves_checkpoint_and_failure_context tests/contract/test_engine_contracts.py::test_system_question_and_failed_events_validate_strictly tests/runtime/test_compatibility_runtime.py::test_filesystem_checkpoint_store_roundtrips_failure_context`
- `PYTHONDONTWRITEBYTECODE=1 python3 -B -m py_compile core/errors.py core/engine.py tests/contract/test_engine_contracts.py`
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q tests/contract/test_engine_contracts.py::test_invalid_goto_after_state_mutation_preserves_state_and_failure_context tests/contract/test_engine_contracts.py::test_after_hook_request_input_checkpoints_pending_input_and_resume_validates_input tests/contract/test_engine_contracts.py::test_resume_invalid_pending_input_preserves_checkpoint_and_failure_context tests/contract/test_engine_contracts.py::test_system_question_and_failed_events_validate_strictly tests/unit/test_provider_retries.py tests/unit/test_simple_surface.py::test_simple_context_suppresses_unmodeled_item_state_surfaces tests/unit/test_simple_surface.py::test_simple_context_exposes_modeled_item_state_surfaces tests/unit/test_simple_surface.py::test_simple_context_step_item_state_runtime_fields_are_read_only tests/runtime/test_compatibility_runtime.py::test_filesystem_checkpoint_store_roundtrips_failure_context`

## Deduplication / centralization
- Centralized failure-context normalization in `FailureContext` and engine helper methods instead of per-site private exception annotations.
- Centralized generic exception metadata attachment in `Engine._annotate_execution_error` so hook/finalization/runtime-control failures share one preservation path.
- Centralized runtime-owned state protection in `Context` via `StateView` instead of duplicating field guards across step implementations.
